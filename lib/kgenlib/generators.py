"""Generator registration and handling functionality."""

import contextvars
import functools
import logging
import os
from importlib import import_module
from inspect import isclass
from pkgutil import iter_modules
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, cast

from kapitan.inputs.kadet import BaseModel, current_target
from kapitan.inputs.kadet import Dict as KadetDict

from .models import GeneratorParams, GeneratorFunctionParams

logger = logging.getLogger(__name__)

# Type definitions for better code clarity
GeneratorFunction = Callable[..., Any]
GeneratorRegistry = Dict[str, List[Tuple[GeneratorFunction, GeneratorParams]]]

# Context variables for thread-safety
registered_generators = contextvars.ContextVar(
    "current registered_generators in thread", default={}
)
try:
    target = current_target.get()
except LookupError:
    # Provide a default value or handle the error gracefully
    target = "default_target"

# Cache of imported generator classes
_imported_generators: Dict[str, Type] = {}


@functools.lru_cache
def load_generators(name: str, path: str) -> Dict[str, Type]:
    """
    Loads all classes from modules in a package and returns them as a dictionary.

    Args:
        name: The name of the package.
        path: The path to the package directory.

    Returns:
        Dictionary mapping class names to class types

    Raises:
        ImportError: If an error occurs while loading a module.
    """
    package_dir = os.path.abspath(os.path.dirname(path))
    imported_classes: Dict[str, Type] = {}
    
    for _, module_name, _ in iter_modules([package_dir]):
        try:
            module = import_module(f"{name}.{module_name}")
            
            # Find all classes defined in this module
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                
                # Only include actual classes defined in this module 
                if (isclass(attribute) and 
                    attribute.__module__ == f"{name}.{module_name}" and
                    not attribute_name.startswith("_")):
                    # Store in our return dictionary
                    imported_classes[attribute_name] = attribute
                    
                    # Also cache it globally for reuse
                    _imported_generators[attribute_name] = attribute
                    
            logger.debug(f"Loaded module {module_name} with {len(imported_classes)} classes")
            
        except Exception as e:
            logger.error(f"Error loading module {module_name}: {e}")
            raise ImportError(f"Failed to import module {module_name}: {e}")
    
    return imported_classes


def get_generator_class(name: str) -> Optional[Type]:
    """
    Get a generator class by name, using cache if available.
    
    Args:
        name: The name of the generator class
        
    Returns:
        The generator class if found, None otherwise
    """
    return _imported_generators.get(name)


def register_function(func: GeneratorFunction, params: GeneratorParams) -> None:
    """
    Registers a function with its associated parameters for a specific target.

    Args:
        func: The function to register.
        params: The parameters associated with the function.
    """
    current_target_name = current_target.get()
    if not current_target_name:
        logger.warning(f"Cannot register function {func.__name__} - no current target")
        return
        
    logger.debug(f"Registering function {func.__name__} with params {params} for target {current_target_name}")

    # Get the current registry and update it atomically
    generator_dict = cast(GeneratorRegistry, registered_generators.get())
    generator_list = generator_dict.setdefault(current_target_name, [])
    generator_list.append((func, params))

    logger.debug(f"Currently registered {len(generator_list)} functions for target {current_target_name}")
    registered_generators.set(generator_dict)


def register_generator(*, 
                      path: Optional[str] = None, 
                      apply_patches: Optional[List[str]] = None, 
                      global_generator: bool = False, 
                      activation_path: Optional[str] = None, 
                      **kwargs) -> Callable[[GeneratorFunction], GeneratorFunction]:
    """
    Decorator to register a generator function with associated parameters.

    Args:
        path: The JMESPath expression to locate configurations in the inventory
        apply_patches: List of JMESPath expressions for patch locations
        global_generator: Whether this generator applies globally
        activation_path: Path to check for activation condition
        **kwargs: Additional parameters for the generator

    Returns:
        A decorator function that registers the decorated function

    Example:
        @register_generator(path="generators.my_generator", apply_patches=["patches.common"])
        def my_generator_function(params):
            # Generator implementation
            pass
    """
    # Create parameters object with provided arguments
    params = GeneratorParams(
        path=path or "",
        apply_patches=apply_patches or [],
        global_generator=global_generator,
        activation_path=activation_path,
        **kwargs
    )
    
    def decorator(func: GeneratorFunction) -> GeneratorFunction:
        """Register the function and return it unchanged."""
        register_function(func, params)
        return func

    return decorator


T = TypeVar('T', bound=BaseModel)

class GeneratorClass(BaseModel):
    """Base class for generator classes."""
    meta: Optional[GeneratorFunctionParams] = None

    @classmethod
    def generate(cls: Type[T], meta: GeneratorFunctionParams) -> T:
        """
        Creates an instance of the generator class with the given metadata.

        Args:
            meta: Metadata for the generator.

        Returns:
            An instance of the generator class.
        """
        return cls(meta=meta)
    
    @property
    def config(self) -> KadetDict[str, Any]:
        """
        Get the configuration from the metadata.
        
        Returns:
            Configuration dictionary or empty dict if no metadata
        """
        if self.meta and hasattr(self.meta, "config"):
            return KadetDict(self.meta.config)
        return KadetDict({})
    
    @property
    def name(self) -> str:
        """
        Get the name from the metadata.
        
        Returns:
            Name string or empty string if no metadata
        """
        if self.meta and hasattr(self.meta, "name"):
            return self.meta.name
        return ""
        
    def get_config(self) -> KadetDict[str, Any]:
        """
        Get the configuration from the metadata.
        
        Returns:
            Configuration dictionary or empty dict if no metadata
        """
        return self.config
        
    def get_inventory(self) -> Dict[str, Any]:
        """
        Get the inventory from the metadata.
        
        Returns:
            Inventory dictionary or empty dict if no metadata
        """
        if self.meta and hasattr(self.meta, "inventory"):
            return self.meta.inventory
        return {}


def get_generators_for_target(target_name: Optional[str] = None) -> List[Tuple[GeneratorFunction, GeneratorParams]]:
    """
    Get all registered generators for a specific target.
    
    Args:
        target_name: The target name (defaults to current target)
        
    Returns:
        List of (generator_function, generator_params) tuples
    """
    generator_dict = cast(GeneratorRegistry, registered_generators.get())
    if target_name is None:
        target_name = current_target.get()
    
    return generator_dict.get(target_name, [])


def expand_and_run(target_name: str, inventory: Dict[str, Any], global_inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Expand and run all generators for a target.
    
    Args:
        target_name: Name of the target
        inventory: Target inventory
        global_inventory: Global inventory data
        
    Returns:
        Updated inventory with generator results
    """
    generators = get_generators_for_target(target_name)
    result = inventory.copy()
    
    if not generators:
        logger.debug(f"No generators registered for target {target_name}")
        return result
        
    logger.info(f"Running {len(generators)} generators for target {target_name}")
    
    for generator_func, params in generators:
        try:
            # Extract configuration using the JMESPath in params.path
            # Run the generator function
            # Apply results to the inventory
            # (Simplified implementation)
            logger.debug(f"Running generator {generator_func.__name__}")
            # Implementation details would go here
        except Exception as e:
            logger.error(f"Error running generator {generator_func.__name__}: {e}")
    
    return result