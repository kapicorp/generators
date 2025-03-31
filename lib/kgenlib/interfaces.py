"""
Common interfaces and mixins for kgenlib.

This module provides reusable interface components that can be used
across different classes in the kgenlib package for consistent APIs.
"""

import contextlib
from typing import Any, Dict, List, Optional, TypeVar, Generic, Iterator, Union

import yaml
import json

from .models import ContentType
from .utils import render_json, render_yaml

# Type variables for generics
T = TypeVar('T')
ContentObj = TypeVar('ContentObj', bound='ContentMixin')


class ContentMixin:
    """
    Mixin with common content operations.
    
    This mixin provides a common interface for working with content objects,
    regardless of their specific implementation details. It defines methods
    for serialization, conversion, and format handling.
    
    Classes that implement this mixin should define:
    - to_dict(): Method that returns a dictionary representation
    """
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        raise NotImplementedError("Implementing classes must define to_dict()")
        
    def to_yaml(self) -> str:
        """
        Convert to YAML representation.
        
        Returns:
            YAML string representation
            
        Example:
            >>> content = SomeContent({"data": "value"})
            >>> print(content.to_yaml())
            data: value
        """
        return render_yaml(self.to_dict())
        
    def to_json(self) -> str:
        """
        Convert to JSON representation.
        
        Returns:
            JSON string representation
            
        Example:
            >>> content = SomeContent({"data": "value"})
            >>> print(content.to_json())
            {
                "data": "value"
            }
        """
        return render_json(self.to_dict())
        
    def get_content_type(self) -> ContentType:
        """
        Get the content type.
        
        Returns:
            The content type (YAML, JSON, RAW)
        """
        return getattr(self, "content_type", ContentType.YAML)
        
    def get_output(self) -> str:
        """
        Get the content in its preferred output format based on content_type.
        
        Returns:
            Content formatted according to its content_type
        """
        content_type = self.get_content_type()
        
        if content_type == ContentType.JSON:
            return self.to_json()
        elif content_type == ContentType.YAML:
            return self.to_yaml()
        else:
            # RAW or other types
            return str(self.to_dict())
            
    def write_to_file(self, filename: Optional[str] = None) -> str:
        """
        Write content to a file using the appropriate format.
        
        Args:
            filename: Path where to write the file (uses self.filename if None)
            
        Returns:
            The path to the written file
            
        Raises:
            ValueError: If no filename is provided and self.filename is not set
            IOError: If writing to the file fails
        """
        from .utils import ensure_dir_exists
        import os
        
        # Get the filename to use
        if filename is None:
            filename = getattr(self, "filename", None)
            
        if not filename:
            raise ValueError("No filename provided for writing content")
            
        # Ensure directory exists
        directory = os.path.dirname(os.path.abspath(filename))
        ensure_dir_exists(directory)
        
        # Get content based on type
        content = self.get_output()
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return filename

    @classmethod
    def from_file(cls, filename: str) -> 'ContentMixin':
        """
        Create a content object from a file.
        
        Args:
            filename: Path to the file to load
            
        Returns:
            A new instance with the content from the file
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is not supported
        """
        import os
        
        if not os.path.exists(filename):
            raise FileNotFoundError(f"File not found: {filename}")
            
        # Determine the file type based on extension
        _, ext = os.path.splitext(filename)
        
        with open(filename, 'r', encoding='utf-8') as f:
            if ext.lower() in ('.yml', '.yaml'):
                return cls.from_dict(yaml.safe_load(f))
            elif ext.lower() == '.json':
                return cls.from_dict(json.load(f))
            else:
                raise ValueError(f"Unsupported file format: {ext}")
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ContentMixin':
        """Create a content object from a dictionary."""
        raise NotImplementedError("Implementing classes must define from_dict()")


class ResourceCollection(Generic[ContentObj]):
    """
    A collection of content resources with filtering and bundling capabilities.
    
    This class provides a consistent way to work with multiple content objects,
    including filtering, grouping, and batch operations.
    
    Attributes:
        resources: List of content objects in the collection
        
    Examples:
        >>> collection = ResourceCollection()
        >>> collection.add(deployment1)
        >>> collection.add(deployment2)
        >>> collection.add(service)
        >>> deployments = collection.filter_by(lambda x: x.root.kind == "Deployment")
        >>> deployments.write_bundle("deployments.yaml")
    """
    
    def __init__(self):
        """Initialize an empty collection."""
        self.resources: List[ContentObj] = []
        
    def add(self, resource: ContentObj) -> None:
        """
        Add a resource to the collection.
        
        Args:
            resource: The content object to add
        """
        self.resources.append(resource)
        
    def add_all(self, resources: List[ContentObj]) -> None:
        """
        Add multiple resources to the collection.
        
        Args:
            resources: List of content objects to add
        """
        self.resources.extend(resources)
        
    def filter_by(self, predicate: callable) -> 'ResourceCollection[ContentObj]':
        """
        Create a new collection with resources that match the predicate.
        
        Args:
            predicate: Function that takes a resource and returns a boolean
            
        Returns:
            New collection with matching resources
        """
        result = ResourceCollection()
        result.add_all([r for r in self.resources if predicate(r)])
        return result
        
    def filter_by_kind(self, kind: str) -> 'ResourceCollection[ContentObj]':
        """
        Create a new collection with resources of a specific kind.
        
        Args:
            kind: The resource kind to filter by
            
        Returns:
            New collection with resources of the specified kind
        """
        return self.filter_by(lambda r: r.root.get('kind') == kind)
        
    def filter_by_label(self, label_key: str, label_value: Optional[str] = None) -> 'ResourceCollection[ContentObj]':
        """
        Create a new collection with resources having a specific label.
        
        Args:
            label_key: The label key to filter by
            label_value: The label value to match (if None, just checks for key)
            
        Returns:
            New collection with resources having the specified label
        """
        def has_label(resource):
            labels = resource.root.get('metadata', {}).get('labels', {})
            if label_value is None:
                return label_key in labels
            return labels.get(label_key) == label_value
                
        return self.filter_by(has_label)
        
    def write_bundle(self, filename: str) -> str:
        """
        Write all resources to a single file as a YAML bundle.
        
        Args:
            filename: Path where to write the bundle
            
        Returns:
            The path to the written file
            
        Raises:
            IOError: If writing to the file fails
        """
        from .utils import ensure_dir_exists
        import os
        
        # Ensure directory exists
        directory = os.path.dirname(os.path.abspath(filename))
        ensure_dir_exists(directory)
        
        # Convert all resources to dicts
        resource_dicts = [r.to_dict() for r in self.resources]
        
        # Create YAML bundle
        content = yaml.dump_all(
            resource_dicts, 
            default_flow_style=False
        )
        
        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return filename
        
    def __len__(self) -> int:
        """Get number of resources in the collection."""
        return len(self.resources)
        
    def __iter__(self) -> Iterator[ContentObj]:
        """Iterate over resources in the collection."""
        return iter(self.resources)


class ContextManagers:
    """Collection of context managers for kgenlib operations."""
    
    @staticmethod
    @contextlib.contextmanager
    def inventory_context(inventory: Optional[Dict] = None) -> Iterator[Dict]:
        """
        Context manager for working with a specific inventory.
        
        This temporarily changes the current inventory and restores it afterward.
        
        Args:
            inventory: The inventory to use within the context
            
        Yields:
            The active inventory
            
        Example:
            >>> with ContextManagers.inventory_context({"custom": "inventory"}):
            ...     # Operations using custom inventory
            ...     generate_resources()
        """
        from kapitan.inputs.kadet import inventory_global
        
        # Get the current inventory
        current_inventory = inventory_global.get()
        
        try:
            # Set the new inventory if provided
            if inventory is not None:
                inventory_global.set(inventory)
                
            # Yield the active inventory
            yield inventory_global.get()
        finally:
            # Restore the original inventory
            inventory_global.set(current_inventory)
            
    @staticmethod
    @contextlib.contextmanager
    def error_handling(default_value: T = None, log_errors: bool = True) -> Iterator[Union[Any, T]]:
        """
        Context manager for error handling.
        
        Catches exceptions and returns a default value instead.
        
        Args:
            default_value: Value to return if an exception occurs
            log_errors: Whether to log exceptions
            
        Yields:
            A context where exceptions are caught and handled
            
        Example:
            >>> with ContextManagers.error_handling(default_value={}):
            ...     # Code that might raise exceptions
            ...     result = process_data()
        """
        try:
            yield
        except Exception as e:
            if log_errors:
                import logging
                logging.getLogger(__name__).warning(f"Operation failed: {e}")
            return default_value
    
    @staticmethod
    @contextlib.contextmanager
    def mutation_batch(content: 'ContentMixin') -> Iterator[None]:
        """
        Context manager for batching multiple mutations on a content object.
        
        This can be used to optimize operations that would otherwise
        require multiple processing passes on the content.
        
        Args:
            content: The content object to mutate
            
        Yields:
            None
            
        Example:
            >>> with ContextManagers.mutation_batch(my_content):
            ...     my_content.patch({"metadata": {"labels": {"app": "example"}}})
            ...     my_content.patch({"spec": {"replicas": 3}})
        """
        # Disable intermediate processing if supported
        original_prune = getattr(content, "prune", True)
        if hasattr(content, "prune"):
            content.prune = False
            
        try:
            yield
        finally:
            # Restore original state and do final processing
            if hasattr(content, "prune"):
                content.prune = original_prune
            
            # Final processing (e.g., pruning if needed)
            if original_prune and hasattr(content, "dump"):
                content.dump()