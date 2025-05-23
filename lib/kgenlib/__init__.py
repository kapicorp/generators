# pylint: disable=logging-fstring-interpolation

import contextvars
import functools
import json
import logging
import os
import re
from enum import Enum
from importlib import import_module
from inspect import isclass
from pkgutil import iter_modules
from typing import Annotated, Callable, List, Optional

import jmespath
import pydantic
import yaml
from box.exceptions import BoxValueError
from kapitan.cached import args
from kapitan.inputs.helm import HelmChart
from kapitan.inputs.kadet import (
    BaseModel,
    BaseObj,
    CompileError,
    Dict,
    current_target,
    inventory_global,
)
from kapitan.utils import prune_empty, render_jinja2_file

logger = logging.getLogger(__name__)

search_paths = args.get("search_paths") if type(args) is dict else args.search_paths
registered_generators = contextvars.ContextVar(
    "current registered_generators in thread", default={}
)

target = current_target.get()


class GeneratorParams(pydantic.BaseModel):
    """
    Represents parameters for a generator function.

    Attributes:
        path (str): The JMESPath expression to locate configurations in the inventory.
        apply_patches: A list of JMESPath expressions to locate patches to apply to the configurations. Defaults to [].
        global_generator: Indicates if the generator should be applied globally to all inventories. Defaults to False.
        activation_path: A JMESPath expression that, if evaluated to True in the inventory, activates the global generator. Defaults to None.
    """

    path: str
    apply_patches: Optional[List[str]] = []
    global_generator: Optional[bool] = False
    activation_path: Optional[str] = None


class GeneratorFunctionParams(pydantic.BaseModel):
    """
    Represents parameters for a generator function.

    Attributes:
        target (str): The target environment or system for the generator.
        id (str): A unique identifier for the generator function.
        name (str): A descriptive name for the generator function.
        config (dict): The configuration data for the generator.
        function (str): The name or identifier of the generator function.
        params (GeneratorParams): Parameters specific to the generator function.
        defaults (dict): Default values for the generator function.
        inventory (dict): The inventory data for the generator.
        global_inventory (dict): The global inventory data.
    """

    target: str
    id: str
    name: str
    config: dict
    function: str
    params: GeneratorParams
    defaults: dict
    inventory: dict
    global_inventory: dict


@functools.lru_cache
def load_generators(name, path):
    """
    Loads all classes from modules in a package and adds them to the global namespace.

    This function iterates through all modules in the specified package, imports them,
    and then adds any classes defined in those modules to the global namespace.
    This allows these classes to be accessed directly by name, without needing to
    know the specific module they are defined in.

    The function uses `lru_cache` to cache the results, so subsequent calls with
    the same arguments will be faster.

    Args:
        name (str): The name of the package.
        path (str): The path to the package directory.

    Raises:
        Exception: If an error occurs while loading a module.
    """

    package_dir = os.path.abspath(os.path.dirname(path))
    for _, module_name, _ in iter_modules([package_dir]):
        try:
            module = import_module(f"{name}.{module_name}")
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                if isclass(attribute):
                    globals()[attribute_name] = attribute

        except Exception as e:
            logger.error(f"Error loading {module_name}: {e}")


class DeleteContent(Exception):
    """
    Raised when content should be deleted.

    This exception is used to signal that a piece of content should be deleted.
    It can be raised in situations where content is found to be invalid,
    inappropriate, or otherwise undesirable.

    Example:
        if content_is_invalid(content):
            raise DeleteContent("Content is invalid and should be deleted.")
    """

    pass


def render_jinja(filename, ctx):
    return render_jinja2_file(filename, ctx, search_paths=search_paths)


def render_json(data):
    if isinstance(data, str):
        data = json.loads(data)
    return json.dumps(data, indent=4, sort_keys=True)


def render_yaml(data):
    if isinstance(data, str):
        data = yaml.safe_load(data)
    return yaml.dump(data, default_flow_style=False, width=1000, sort_keys=True)


def findpath(obj, path: str, default={}):
    """
    Safely extracts a value from a JSON-like object using a JMESPath expression.

    This function attempts to extract a value from the given object using the
    provided JMESPath expression. If the expression is empty or an error occurs
    during the search, it returns the provided default value.

    Args:
        obj (dict or list): The JSON-like object to search.
        path (str): The JMESPath expression to use for searching.
        default (Any, optional): The value to return if the path is empty or
                                 an error occurs. Defaults to None.

    Returns:
        Any: The extracted value or the default value.

    Examples:
        >>> findpath({"a": {"b": 1}}, "a.b")
        1
        >>> findpath({"a": {"b": 1}}, "c.d", default=0)
        0
    """
    try:
        value = jmespath.search(path, obj)
    except jmespath.exceptions.EmptyExpressionError:
        return default  # Return default directly on empty expression error

    return value if value is not None else default


def merge(source: Dict, destination: Dict) -> Dict:
    """
    Recursively merges two dictionaries.

    This function merges the `source` dictionary into the `destination` dictionary,
    giving precedence to values in the `source` dictionary in case of conflicts.
    It handles nested dictionaries by recursively merging them.

    If a key in the `source` dictionary has a corresponding value in the
    `destination` dictionary that is an empty dictionary, the value from the
    `source` dictionary is ignored (this allows for intentional overriding).

    Args:
        source (Dict): The source dictionary to merge from.
        destination (Dict): The destination dictionary to merge into.

    Returns:
        Dict: The merged dictionary.
    """
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.get(key, None)
            if node is None:
                destination[key] = value
            elif len(node) == 0:
                # node is set to an empty dict on purpose as a way to override the value
                pass
            else:
                merge(value, node)
        else:
            destination[key] = destination.setdefault(key, value)

    return destination


def patch_config(config: Dict, inventory: Dict, inventory_path: str) -> None:
    """
    Applies a patch to a configuration.

    This function extracts a patch from the inventory using the provided
    `inventory_path` and applies it to the `config` dictionary using the
    `deep_merge` function.

    Args:
        config (Dict): The configuration dictionary to patch.
        inventory (Dict): The inventory dictionary containing the patch.
        inventory_path (str): The JMESPath expression to locate the patch in the inventory.
    """
    patch = findpath(inventory, inventory_path, {})
    logger.debug(f"Applying patch {inventory_path} : {patch}")
    merge(patch, config)


def register_function(func: Callable, params: GeneratorParams):
    """
    Registers a function with its associated parameters for a specific target.

    This function takes a function and its parameters, retrieves the current target
    from a context variable, and stores the function-parameter pair in a dictionary
    associated with that target. This dictionary is also stored in a context variable.

    Args:
        func (Callable): The function to register.
        params (GeneratorParams): The parameters associated with the function.
    """
    target = current_target.get()

    logger.debug(
        f"Registering function {func.__name__} with params {params} for target {target}"
    )

    generator_dict = registered_generators.get()
    generator_list = generator_dict.setdefault(
        target, []
    )  # Use setdefault for cleaner initialization
    generator_list.append((func, params))

    logger.debug(
        f"Currently registered {len(generator_list)} functions for target {target}"
    )

    registered_generators.set(generator_dict)


def register_generator(*args, **kwargs):
    """
    Decorator to register a generator function with associated parameters.

    This decorator simplifies the registration of generator functions by taking
    any arguments and keyword arguments that should be associated with the
    generator. It then uses the `register_function` to store the function and
    its parameters for later use.

    Args:
        *args: Any positional arguments to be associated with the generator.
        **kwargs: Any keyword arguments to be associated with the generator.

    Returns:
        Callable: A wrapped function that returns the original generator function.

    Example:
        @register_generator(param1="value1", param2="value2")
        def my_generator():
            # ... generator logic ...
            yield something
    """

    def wrapper(func):
        register_function(
            func, GeneratorParams(**kwargs)
        )  # Register the function with its parameters

        def wrapped_func():
            return func  # Return the original function

        return wrapped_func

    return wrapper


class GeneratorClass(BaseModel):
    """
    Base class for generator classes.

    This class provides a standard way to define and instantiate generator classes
    with optional metadata.

    Attributes:
        meta (Optional[GeneratorFunctionParams]): Optional metadata for the generator.
    """

    meta: Optional[GeneratorFunctionParams] = None

    @classmethod
    def generate(cls, meta: GeneratorFunctionParams):
        """
        Creates an instance of the generator class with the given metadata.

        Args:
            meta (GeneratorFunctionParams): Metadata for the generator.

        Returns:
            GeneratorClass: An instance of the generator class.
        """
        return cls(**meta)


MutationCondition = Annotated[
    dict[str, list[str]],
    "A dictionary where keys are strings and values are lists of strings",
]


class RegExpMatchMutationSpec(BaseModel):
    patch: dict
    conditions: MutationCondition


class PatchMutationSpec(BaseModel):
    patch: dict
    conditions: MutationCondition


class BundleMutationSpec(BaseModel):
    filename: str
    conditions: MutationCondition
    break_: bool = pydantic.Field(alias="break", default=True)


class DeleteMutationSpec(BaseModel):
    conditions: MutationCondition


class PruneMutationSpec(BaseModel):
    prune: bool = True
    conditions: MutationCondition
    break_: bool = pydantic.Field(alias="break", default=True)


class ContentMutateSpec(BaseModel):
    regex_patch: Optional[list[RegExpMatchMutationSpec]] = []
    patch: Optional[list[PatchMutationSpec]] = []
    bundle: Optional[list[BundleMutationSpec]] = []
    delete: Optional[list[DeleteMutationSpec]] = []
    prune: Optional[list[PruneMutationSpec]] = []


class ContentType(Enum):
    YAML = 1
    KUBERNETES_RESOURCE = 2
    TERRAFORM_BLOCK = 3
    JSON = 4


class BaseContent(GeneratorClass):
    content_type: ContentType = ContentType.YAML
    filename: str = "output"
    prune: bool = True

    def body(self):
        pass

    def dump(self):
        if self.prune:
            self.root = Dict(prune_empty(self.root))
        return super().dump()

    @classmethod
    def from_baseobj(cls, baseobj: BaseObj):
        """Return a BaseContent initialised with baseobj."""
        return cls.from_dict(baseobj.root)

    @classmethod
    def from_yaml(cls, file_path) -> List:
        """Returns a list of BaseContent initialised with the content of file_path data."""

        content_list = list()
        with open(file_path) as fp:
            yaml_objs = yaml.safe_load_all(fp)
            for yaml_obj in yaml_objs:
                if yaml_obj:
                    content_list.append(BaseContent.from_dict(yaml_obj))

        return content_list

    @classmethod
    def from_dict(cls, dict_value):
        """Return a BaseContent initialised with dict_value."""

        if dict_value:
            try:
                obj = cls()
                obj.parse(Dict(dict_value))
                return obj
            except BoxValueError as e:
                raise CompileError(
                    f"error when importing item '{dict_value}' of type {type(dict_value)}: {e}"
                )

    def parse(self, content: Dict):
        self.root = content

    @staticmethod
    def findpath(obj, path):
        return findpath(obj, path)

    def mutate(self, mutations: ContentMutateSpec):
        mutations = ContentMutateSpec.model_validate(mutations)
        for action in mutations.patch:
            if self.match(action.conditions):
                self.patch(action.patch)

        for action in mutations.regex_patch:
            if self.match(action.conditions):
                self.regex_patch(action.patch)

        for action in mutations.delete:
            if self.match(action.conditions):
                raise DeleteContent(f"Deleting {self} because of {action.conditions}")

        for action in mutations.prune:
            if self.match(action.conditions):
                self.prune = action.prune
                if action.break_:
                    break
        for action in mutations.bundle:
            if self.match(action.conditions):
                try:
                    self.filename = action.filename.format(content=self)
                except (AttributeError, KeyError):
                    pass
                if action.break_:
                    break

    def match(self, match_conditions):
        for key, values in match_conditions.items():
            if "*" in values:
                return True
            value = self.findpath(self.root, key)
            if value in values:
                continue
            else:
                return False
        return True

    def patch(self, patch):
        self.root.merge_update(Dict(patch), box_merge_lists="extend")

    def regex_patch(self, patch):
        if not isinstance(patch, dict):
            raise CompileError(
                "Expected dict[pattern: str, replacement: str] for regex_patch"
            )
        yaml_dump: str = yaml.dump(self.dump())
        for pattern, replacement in patch.items():
            yaml_dump = re.sub(pattern, replacement, yaml_dump)

        patched_dict = yaml.safe_load(yaml_dump)
        self.parse(Dict(patched_dict))


class BaseStore(GeneratorClass):
    content_list: List[BaseContent] = []

    @classmethod
    def from_yaml_file(cls, file_path):
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

    def add(self, object):
        logger.debug(f"Adding {type(object)} to store")
        if isinstance(object, BaseContent):
            self.content_list.append(object)
        elif isinstance(object, BaseStore):
            self.content_list.extend(object.content_list)

        elif isinstance(object, list):
            for item in object:
                if isinstance(item, BaseObj):
                    self.add(BaseContent.from_baseobj(item))
                else:
                    self.add_list(item)

        elif isinstance(object, BaseObj):
            self.add(BaseContent.from_baseobj(object))

        else:
            self.content_list.append(object)

    def add_list(self, contents: List[BaseContent]):
        for content in contents:
            self.add(content)

    def import_from_helm_chart(self, **kwargs):
        self.add_list(
            [
                BaseContent.from_baseobj(resource)
                for resource in HelmChart(**kwargs).root.values()
            ]
        )

    def apply_patch(self, patch: Dict):
        for content in self.get_content_list():
            content.patch(patch)

    def process_mutations(self, mutations: Dict):
        for content in self.get_content_list():
            try:
                content.mutate(mutations)
            except DeleteContent as e:
                logger.debug(e)
                self.content_list.remove(content)
            except:
                raise CompileError(f"Error when processing mutations on {content}")

    def get_content_list(self):
        return getattr(self, "content_list", [])

    def dump(self, output_filename=None, already_processed=False):
        """Return object dict/list."""
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
                        f"Skipping duplicated content content for reason 'Duplicate name {content.name} for {filename}'"
                    )
                    continue

                self.root.setdefault(filename, []).append(content)

        return super().dump()


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
        """
        self.inventory = inventory
        self.global_inventory = inventory_global()
        self.generator_defaults = findpath(self.inventory, defaults_path)
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
        generator_function_params = {
            "target": current_target.get(),
            "id": generator_config_id,
            "name": generator_config.get("name", generator_config_id),
            "config": generator_config,
            "function": generator_function.__name__,
            "params": generator_params,
            "defaults": self.generator_defaults,
            "inventory": inventory,
            "global_inventory": self.global_inventory,
        }
        logger.debug(
            f"Running class {generator_function.__name__} for {generator_config_id} with params {list(generator_function_params.keys())}"
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
        configs = findpath(inventory.parameters, generator_params.path)

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
        generators = registered_generators.get().get(target, [])
        logger.debug(
            f"{len(generators)} classes registered as generators for target {target}"
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

            # Get the current target name for global_target filtering
            current_target_name = current_target.get()

            for target_name, inventory in self.global_inventory.items():

                # For other targets, check global_target parameter
                inventory_global_target = findpath(inventory.parameters, "global_target")

                # Process if: global_target not set/empty (backward compatibility)
                # OR global_target matches current target
                # OR it's the current target
                if (not inventory_global_target
                        or inventory_global_target == current_target_name
                        or target_name == current_target_name):
                    logger.debug(
                        f"Processing inventory {target_name} "
                        f"(global_target={inventory_global_target or 'not set'})"
                    )
                    self.expand_and_run(
                        generator_function=func,
                        generator_params=params,
                        inventory=inventory,
                    )
                else:
                    logger.debug(
                        f"Skipping inventory {target_name} (global_target={inventory_global_target}) "
                        f"- not listening to current target {current_target_name}"
                    )
        else:
            logger.debug(
                f"Skipping global generator {func.__name__} with params {params}"
            )