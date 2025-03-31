
import os
import yaml
import logging
from typing import List, Dict, Any, Optional, ClassVar, Type, TypeVar, Callable
from pydantic import BaseModel, Field

from kapitan.inputs.kadet import BaseObj, CompileError
from kapitan.inputs.helm import HelmChart

from .exceptions import DeleteContent
from .generators import GeneratorClass, registered_generators
from .models import ContentMutateSpec, GeneratorParams, GeneratorFunctionParams
from .content import BaseContent
from .contexts import current_target, inventory_global
from .utils import findpath, merge

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='BaseStore')

class BaseStore(GeneratorClass):
    """
    A container for managing multiple content objects.
    Provides functionality for loading, storing, and manipulating content.
    """
    content_list: List[BaseContent] = []
    root: Dict[str, List[BaseContent]] = {}

    @classmethod
    def from_yaml_file(cls: Type[T], file_path: str) -> T:
        """
        Create a store instance from a YAML file containing one or more resources.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            A new BaseStore instance populated with content from the file
        """
        store = cls()
        with open(file_path) as fp:
            basename = os.path.basename(file_path)
            filename = os.path.splitext(basename)[0]
            yaml_objs = yaml.safe_load_all(fp)
            for yaml_obj in yaml_objs:
                if yaml_obj:
                    content = BaseContent.from_dict(yaml_obj)
                    content.filename = filename
                    store.add(content)
        return store

    def add(self, obj: Any) -> None:
        """
        Add content to the store.
        
        Args:
            obj: Content to add (BaseContent, BaseStore, list, or BaseObj)
        """
        logger.debug(f"Adding {type(obj)} to store")
        if isinstance(obj, BaseContent):
            self.content_list.append(obj)
        elif isinstance(obj, BaseStore):
            self.content_list.extend(obj.content_list)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, BaseObj):
                    self.add(BaseContent.from_baseobj(item))
                else:
                    self.add_list(item)
        elif isinstance(obj, BaseObj):
            self.add(BaseContent.from_baseobj(obj))
        else:
            self.content_list.append(obj)

    def add_list(self, contents: List[BaseContent]) -> None:
        """
        Add multiple content items to the store.
        
        Args:
            contents: List of content objects to add
        """
        for content in contents:
            self.add(content)

    def import_from_helm_chart(self, **kwargs) -> None:
        """
        Import resources from a Helm chart.
        
        Args:
            **kwargs: Arguments to pass to HelmChart constructor
        """
        self.add_list(
            [
                BaseContent.from_baseobj(resource)
                for resource in HelmChart(**kwargs).root.values()
            ]
        )

    def apply_patch(self, patch: Dict) -> None:
        """
        Apply a patch to all content items in the store.
        
        Args:
            patch: Patch to apply
        """
        for content in self.get_content_list():
            content.patch(patch)

    def process_mutations(self, mutations: Dict) -> None:
        """
        Process mutations on all content items in the store.
        
        Args:
            mutations: Mutations to apply
            
        Raises:
            CompileError: If an error occurs during mutation processing
        """
        for content in self.get_content_list():
            try:
                content.mutate(mutations)
            except DeleteContent as e:
                logger.debug(e)
                self.content_list.remove(content)
            except Exception as ex:
                raise CompileError(f"Error when processing mutations on {content}: {ex}")

    def get_content_list(self) -> List[BaseContent]:
        """
        Get the list of content items in the store.
        
        Returns:
            List of content items
        """
        return getattr(self, "content_list", [])

    def dump(self, output_filename: Optional[str] = None, already_processed: bool = False) -> Dict:
        """
        Return object dict/list and organize content by filename.
        
        Args:
            output_filename: Format string for output filenames
            already_processed: Whether content has already been processed
            
        Returns:
            Dictionary of content organized by filename
        """
        logger.debug(f"Dumping {len(self.get_content_list())} items")
        if not already_processed:
            for content in self.get_content_list():
                if output_filename:
                    output_format = output_filename
                else:
                    output_format = getattr(content, "filename", "output")
                filename = output_format.format(content=content)
                file_content_list = self.root.get(filename, [])
                if content in file_content_list:
                    logger.debug(
                        f"Skipping duplicated content for reason 'Duplicate name {content.name} for {filename}'"
                    )
                    continue

                self.root.setdefault(filename, []).append(content)

        # If GeneratorClass has a dump method, call it, otherwise return self.root
        if hasattr(super(), "dump"):
            return super().dump()
        return self.root

class BaseGenerator:
    """
    Base class for generating configurations based on an inventory.

    This class provides the foundation for generating configurations by processing
    an inventory. It handles the expansion of configuration parameters, application
    of patches, and execution of generator functions.

    Attributes:
        inventory (Dict): The inventory data containing parameters and other information.
        global_inventory (Dict): The global inventory data.
        generator_defaults (Dict): Default values for generator parameters.
        store (BaseStore): An instance of BaseStore to store generated configurations.
    """

    def __init__(
        self,
        inventory: Dict,
        store: Callable[[], "BaseStore"] = None,  # Use Callable for clarity
        defaults_path: str = None,
    ) -> None:
        """
        Initializes the BaseGenerator with inventory data, an optional store,
        and a path to default values.

        Args:
            inventory (Dict): The inventory data.
            store (Callable[[], BaseStore], optional): Factory function for creating a store. Defaults to None.
            defaults_path (str, optional): JMESPath expression to locate default values in the inventory. Defaults to None.
        """
        self.inventory = inventory
        self.global_inventory = inventory_global()
        self.generator_defaults = findpath(self.inventory, defaults_path or "")
        logger.debug(
            f"Setting {self.generator_defaults} as generator defaults for {defaults_path}"
        )

        # Simplified store initialization
        self.store = store() if store else BaseStore()

    def _apply_patches(self, config: Dict, patches: list, inventory: Dict) -> Dict:
        """
        Applies patches to a configuration.

        Args:
            config (Dict): The configuration to patch.
            patches (list): A list of JMESPath expressions to locate patches in the inventory.
            inventory (Dict): The inventory containing the patches.

        Returns:
            Dict: The patched configuration.
        """
        patched_config = Dict(config)
        for path in patches:
            try:
                path = path.format(**patched_config)
                patch = findpath(inventory.parameters, path, {})
                patched_config = merge(patch, patched_config)
            except KeyError:
                logger.debug(f"Key error when applying patch with path {path}")
                pass  # Silently ignore missing keys
        return patched_config

    def _run_generator_function(
        self,
        generator_function: Callable,
        generator_config_id: str,
        generator_config: Dict,
        generator_params: GeneratorParams,
        inventory: Dict,
    ) -> None:
        """
        Executes a generator function with the given configuration and parameters.

        Args:
            generator_function (Callable): The generator function to execute.
            generator_config_id (str): The ID of the configuration.
            generator_config (Dict): The configuration data.
            generator_params (Dict): Additional parameters for the generator function.
            inventory (Dict): The inventory data.
        """
        generator_function_params = GeneratorFunctionParams(
            target=current_target.get(),
            id=generator_config_id,
            name=generator_config.get("name", generator_config_id),
            config=generator_config,
            function=generator_function.__name__,
            params=generator_params,
            defaults=self.generator_defaults,
            inventory=inventory,
            global_inventory=self.global_inventory,
        )
        
        logger.debug(
            f"Running class {generator_function.__name__} for {generator_config_id} with params {list(generator_function_params.dict().keys())}"
        )
        self.store.add(generator_function.generate(meta=generator_function_params))

    def expand_and_run(
        self,
        generator_function: Callable,
        generator_params: GeneratorParams,
        inventory: Dict = None,
    ) -> None:
        """
        Expands configurations based on a 'path' parameter and runs a generator function for each.

        Args:
            generator_function (Callable): The generator function to execute.
            generator_params (GeneratorParams): Generator parameters
            inventory (Dict, optional): The inventory to use. Defaults to self.inventory.
        """
        inventory = inventory or self.inventory
        configs = findpath(inventory.parameters, generator_params.path, {})

        if configs:
            logger.debug(
                f"Found {len(configs)} configs to generate at {generator_params.path} for target {current_target.get()}"
            )
            for generator_config_id, generator_config in configs.items():
                if generator_params.apply_patches:
                    generator_config = self._apply_patches(
                        generator_config, generator_params.apply_patches, inventory
                    )
                self._run_generator_function(
                    generator_function,
                    generator_config_id,
                    generator_config,
                    generator_params,
                    inventory,
                )

    def generate(self) -> "BaseStore":
        """
        Generates configurations by running registered generator functions.

        This method iterates through the registered generator functions, determines
        whether they are global or local generators, and executes them accordingly.
        Global generators are applied to all inventories, while local generators
        are applied only to the current inventory.

        Returns:
            BaseStore: The store containing the generated configurations.
        """
        target_name = current_target.get()
        generators = registered_generators.get().get(target_name, [])
        logger.debug(
            f"{len(generators)} classes registered as generators for target {target_name}"
        )

        for func, params in generators:
            if params.global_generator:
                self._run_global_generator(func, params)
            else:
                logger.debug(f"Expanding {func.__name__} with params {params}")
                self.expand_and_run(generator_function=func, generator_params=params)

        return self.store

    def _run_global_generator(self, func: Callable, params: GeneratorParams) -> None:
        """
        Runs a generator function globally across all inventories.

        Args:
            func (Callable): The generator function to execute.
            params (GeneratorParams): Parameters for the generator function.
        """
        activation_path = params.activation_path
        if activation_path and findpath(self.inventory.parameters, activation_path):
            logger.debug(
                f"Running global generator {func.__name__} with activation path {activation_path}"
            )
            for _, inventory in self.global_inventory.items():
                self.expand_and_run(
                    generator_function=func,
                    generator_params=params,
                    inventory=inventory,
                )
        else:
            logger.debug(
                f"Skipping global generator {func.__name__} with params {params}"
            )
