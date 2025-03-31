"""
Utility functions for the kgenlib package.

This module provides various utility functions for:
- Rendering templates and data formats (Jinja, JSON, YAML)
- Safe data extraction and manipulation
- Dictionary operations like merging and patching
- File handling utilities
"""

import json
import logging
import os
from functools import wraps
from time import time
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast

import jmespath
import jmespath.exceptions
import yaml
from kapitan.utils import prune_empty, render_jinja2_file
from kapitan.cached import args

logger = logging.getLogger(__name__)

# Constants for default values and configuration
DEFAULT_EMPTY_DICT = {}
DEFAULT_EMPTY_LIST = []
DEFAULT_INDENT = 4
YAML_DEFAULT_WIDTH = 1000
DEFAULT_ENCODING = "utf-8"

# Initialize search paths for templates - with defensive coding
search_paths = []  # Default to empty list if not available
if isinstance(args, dict) and "search_paths" in args:
    search_paths = args["search_paths"]
elif hasattr(args, "search_paths"):
    search_paths = args.search_paths

# Type variables for generic functions
T = TypeVar('T')
D = TypeVar('D')  # Default value type


def timed(func: Callable) -> Callable:
    """
    Decorator to measure function execution time.
    
    Args:
        func: The function to time
        
    Returns:
        Wrapped function that logs execution time
        
    Example:
        >>> @timed
        ... def slow_function():
        ...     time.sleep(1)
        ...
        >>> slow_function()
        DEBUG:kgenlib.utils:slow_function took 1.001 seconds
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time()
        result = func(*args, **kwargs)
        end = time()
        logger.debug(f"{func.__name__} took {end - start:.3f} seconds")
        return result
    return wrapper


def safe_call(func: Callable[..., T], *args, default: Optional[D] = None, 
              log_errors: bool = True, **kwargs) -> Union[T, D]:
    """
    Safely call a function with error handling.
    
    Args:
        func: Function to call
        *args: Arguments to pass to the function
        default: Default value to return if function raises an exception
        log_errors: Whether to log exceptions
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Function result or default value on error
        
    Example:
        >>> safe_call(json.loads, '{"valid": "json"}')
        {'valid': 'json'}
        >>> safe_call(json.loads, 'invalid json', default={})
        {}
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"Error calling {func.__name__}: {e}")
        return default


def render_jinja(filename: str, ctx: Dict[str, Any]) -> str:
    """Render a Jinja2 template with the given context."""
    return render_jinja2_file(filename, ctx, search_paths=search_paths)


def render_json(data: Union[str, Dict, list]) -> str:
    """Render data as formatted JSON string."""
    if isinstance(data, str):
        data = json.loads(data)
    return json.dumps(data, indent=DEFAULT_INDENT, sort_keys=True)


def render_yaml(data: Union[str, Dict, list]) -> str:
    """Render data as formatted YAML string."""
    if isinstance(data, str):
        data = yaml.safe_load(data)
    return yaml.dump(data, default_flow_style=False, width=YAML_DEFAULT_WIDTH, sort_keys=True)


def findpath(obj: Any, path: str, default: Any = DEFAULT_EMPTY_DICT) -> Any:
    """
    Safely extracts a value from a JSON-like object using a JMESPath expression.

    This function attempts to extract a value from the given object using the
    provided JMESPath expression. If the expression is empty or an error occurs
    during the search, it returns the provided default value.

    Args:
        obj: The JSON-like object to search.
        path: The JMESPath expression to use for searching.
        default: The value to return if the path is empty or an error occurs.

    Returns:
        The extracted value or the default value.

    Examples:
        >>> findpath({"a": {"b": 1}}, "a.b")
        1
        >>> findpath({"a": {"b": 1}}, "c.d", default=0)
        0
    """
    try:
        value = jmespath.search(path, obj)
    except jmespath.exceptions.EmptyExpressionError:
        return default

    return value if value is not None else default


def merge(source: Dict, destination: Dict) -> Dict:
    """
    Recursively merges two dictionaries.

    This function merges the `source` dictionary into the `destination` dictionary,
    giving precedence to values in the `source` dictionary in case of conflicts.
    It handles nested dictionaries by recursively merging them.

    Args:
        source: The source dictionary to merge from.
        destination: The destination dictionary to merge into.

    Returns:
        The merged dictionary.
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

    Args:
        config: The configuration dictionary to patch.
        inventory: The inventory dictionary containing the patch.
        inventory_path: The JMESPath expression to locate the patch in the inventory.
    """
    patch = findpath(inventory, inventory_path, DEFAULT_EMPTY_DICT.copy())
    logger.debug(f"Applying patch {inventory_path} : {patch}")
    merge(patch, config)