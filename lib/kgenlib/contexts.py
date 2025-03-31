"""
Context managers for kgenlib operations.

This module provides context managers for managing state and handling
operations that require cleanup or restoration of state.
"""

import contextlib
import logging
from typing import Any, Dict, Iterator, Optional, TypeVar, Union, cast

from kapitan.inputs.kadet import current_target, inventory_global

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar('T')


@contextlib.contextmanager
def generator_context(inventory: Optional[Dict] = None):
    """
    Context manager for running generators with a specific inventory.
    
    Args:
        inventory: Optional inventory to use (if None, uses global inventory)
        
    Yields:
        The current inventory
        
    Example:
        ```python
        with generator_context({"config": {"replicas": 3}}):
            # Code here will use the specified inventory
            generator = MyGenerator()
            generator.generate()
        ```
    """
    original_inventory = inventory_global.get()
    try:
        if inventory is not None:
            inventory_global.set(inventory)
        yield inventory_global.get()
    finally:
        inventory_global.set(original_inventory)


@contextlib.contextmanager
def target_context(target_name: Optional[str] = None):
    """
    Context manager for working with a specific target.
    
    Args:
        target_name: Name of the target to use (if None, keeps current target)
        
    Yields:
        The current target name
        
    Example:
        ```python
        with target_context("production"):
            # Code here will use the production target
            resources = generate_resources()
        ```
    """
    original_target = current_target.get()
    try:
        if target_name is not None:
            current_target.set(target_name)
        yield current_target.get()
    finally:
        current_target.set(original_target)


@contextlib.contextmanager
def error_handling(default_value: T = None, log_errors: bool = True) -> Iterator[Union[T, Any]]:
    """
    Context manager for error handling.
    
    This context manager catches exceptions and returns a default value
    instead of allowing the exception to propagate.
    
    Args:
        default_value: Value to return if an exception occurs
        log_errors: Whether to log exceptions
        
    Yields:
        A context where exceptions are caught and handled
        
    Example:
        ```python
        with error_handling(default_value={}):
            result = json.loads(potentially_invalid_json)
        ```
    """
    try:
        yield
    except Exception as e:
        if log_errors:
            logger.warning(f"Operation failed: {e}")
        return cast(T, default_value)


@contextlib.contextmanager
def batch_processing(content_obj: Any):
    """
    Context manager for batching operations on content objects.
    
    This context manager optimizes operations by disabling intermediate
    processing and only performing final processing at the end.
    
    Args:
        content_obj: Content object to batch operations on
        
    Yields:
        The content object
        
    Example:
        ```python
        with batch_processing(my_content):
            # Multiple operations are batched for better performance
            my_content.patch(patch1)
            my_content.patch(patch2)
            my_content.patch(patch3)
        ```
    """
    # Store original state
    original_prune = getattr(content_obj, "prune", True)
    
    # Disable intermediate processing if supported
    if hasattr(content_obj, "prune"):
        content_obj.prune = False
        
    try:
        yield content_obj
    finally:
        # Restore original state
        if hasattr(content_obj, "prune"):
            content_obj.prune = original_prune
            
        # Do final processing if needed
        if original_prune and hasattr(content_obj, "dump"):
            content_obj.dump()