"""
Content handling for kgenlib.

This module defines base classes for content generation and manipulation.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union, TypeVar, cast, Type

import yaml
from box.exceptions import BoxValueError
from jsonpath_ng.ext import parse as parse_jsonpath
from jsonpath_ng.exceptions import JsonPathParserError
from kapitan.inputs.kadet import BaseObj, CompileError, Dict
from kapitan.utils import prune_empty

from .exceptions import DeleteContent
from .generators import GeneratorClass
from .models import ContentMutateSpec, ContentType, PatchAction, RegexPatchAction, DeleteAction, PruneAction, BundleAction
from .utils import findpath
from .interfaces import ContentMixin

logger = logging.getLogger(__name__)

# Type aliases for better readability
ContentDict = Dict
JsonPathMatch = Any  # Replace with actual type when available
T = TypeVar('T', bound='BaseContent')


class BaseContent(GeneratorClass, ContentMixin):
    """
    Base class for content generation.
    
    This class combines generator functionality with content manipulation capabilities.
    """
    content_type: ContentType = ContentType.YAML
    filename: str = "output"
    prune: bool = True

    def body(self) -> None:
        """
        Override this method to define the content body.
        
        This method should be implemented by subclasses to define their specific content.
        """
        pass

    def dump(self) -> Dict:
        """
        Return the processed content.
        
        If prune is True, empty values will be removed from the content.
        
        Returns:
            The processed content as a Dict
        """
        if self.prune:
            self.root = Dict(prune_empty(self.root))
        return super().dump()

    @classmethod
    def from_baseobj(cls: Type[T], baseobj: BaseObj) -> T:
        """Create a new instance from a BaseObj."""
        return cls.from_dict(baseobj.root)

    @classmethod
    def from_yaml(cls: Type[T], file_path: str) -> List[T]:
        """
        Returns a list of BaseContent objects initialized with file_path data.
        
        Args:
            file_path: Path to the YAML file to load
            
        Returns:
            List of BaseContent objects, one for each YAML document in the file
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            yaml.YAMLError: If the file contains invalid YAML
        """
        content_list = []
        with open(file_path) as fp:
            try:
                yaml_objs = yaml.safe_load_all(fp)
                for yaml_obj in yaml_objs:
                    if yaml_obj:
                        content = cls.from_dict(yaml_obj)
                        if content:  # Skip None results
                            content_list.append(content)
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML from {file_path}: {e}")
                raise
                
        return content_list

    @classmethod
    def from_dict(cls: Type[T], dict_value: Dict) -> Optional[T]:
        """
        Return a BaseContent initialized with dict_value.
        
        Args:
            dict_value: Dictionary containing the content
            
        Returns:
            A new instance with the content, or None if dict_value is empty
            
        Raises:
            CompileError: If there's an error creating the object from the dictionary
        """
        if not dict_value:
            return None
            
        try:
            obj = cls()
            obj.parse(Dict(dict_value))
            return obj
        except BoxValueError as e:
            raise CompileError(
                f"Error creating {cls.__name__} from dictionary: {e}. "
                f"Value type: {type(dict_value).__name__}, Value: {dict_value}"
            ) from e

    def parse(self, content: Dict) -> None:
        """
        Parse content into the object.
        
        Args:
            content: The content to parse into this object
        """
        self.root = content

    @staticmethod
    def findpath(obj: Dict, path: str, default: Any = {}) -> Any:
        """
        Find a value at the specified path.
        
        Args:
            obj: The object to search in
            path: JMESPath expression for the search
            default: Value to return if path is not found
            
        Returns:
            The found value or the default
        """
        return findpath(obj, path, default)

    def mutate(self, mutations: ContentMutateSpec) -> None:
        """
        Apply mutations to the content.
        
        This method applies various types of mutations (patch, regex_patch, delete, etc.)
        to the content based on the provided specification.
        
        Args:
            mutations: Specification of mutations to apply
            
        Raises:
            DeleteContent: If a delete mutation matches and requests content deletion
        """
        # Validate and convert mutations
        if not isinstance(mutations, ContentMutateSpec):
            mutations = ContentMutateSpec.model_validate(mutations)
        
        # Apply mutations in sequence, using dedicated methods for each type
        self._apply_patches(mutations.patch)
        self._apply_regex_patches(mutations.regex_patch)
        self._handle_delete_actions(mutations.delete)
        self._handle_prune_actions(mutations.prune)
        self._handle_bundle_actions(mutations.bundle)

    def _apply_patches(self, patch_actions: List[PatchAction]) -> None:
        """
        Apply patch actions to the content.
        
        Args:
            patch_actions: List of patch actions to apply
        """
        for action in patch_actions:
            if self.match(action.conditions):
                self.patch(action.patch, action.path, action.prepend_lists)

    def _apply_regex_patches(self, regex_actions: List[RegexPatchAction]) -> None:
        """
        Apply regex patch actions to the content.
        
        Args:
            regex_actions: List of regex patch actions to apply
        """
        for action in regex_actions:
            if self.match(action.conditions):
                self.regex_patch(action.patch)

    def _handle_delete_actions(self, delete_actions: List[DeleteAction]) -> None:
        """
        Process delete actions, raising DeleteContent if a match is found.
        
        Args:
            delete_actions: List of delete actions to check
            
        Raises:
            DeleteContent: If any delete action matches
        """
        for action in delete_actions:
            if self.match(action.conditions):
                raise DeleteContent(f"Deleting content due to matching condition: {action.conditions}")

    def _handle_prune_actions(self, prune_actions: List[PruneAction]) -> None:
        """
        Process prune actions, updating the prune flag if matches are found.
        
        Args:
            prune_actions: List of prune actions to process
        """
        for action in prune_actions:
            if self.match(action.conditions):
                self.prune = action.prune
                if action.break_:
                    break

    def _handle_bundle_actions(self, bundle_actions: List[BundleAction]) -> None:
        """
        Process bundle actions, updating the filename if matches are found.
        
        Args:
            bundle_actions: List of bundle actions to process
        """
        for action in bundle_actions:
            if self.match(action.conditions):
                try:
                    self.filename = action.filename.format(content=self)
                except (AttributeError, KeyError, ValueError) as e:
                    logger.warning(f"Error formatting filename {action.filename}: {e}")
                if action.break_:
                    break

    def match(self, match_conditions: Dict[str, List[str]]) -> bool:
        """
        Check if the content matches the specified conditions.
        
        Args:
            match_conditions: Dictionary mapping paths to acceptable values
            
        Returns:
            True if all conditions match, False otherwise
            
        Example:
            ```python
            # Check if kind is Deployment and namespace is default
            content.match({
                "kind": ["Deployment"], 
                "metadata.namespace": ["default"]
            })
            ```
        """
        for key, values in match_conditions.items():
            # Wildcard match
            if "*" in values:
                continue
                
            # Get value at path
            value = self.findpath(self.root, key)
            
            # Check if value matches any acceptable value
            if value in values:
                continue
            else:
                return False
                
        # All conditions matched
        return True

    def patch(self, patch: Union[Dict, List], path: Optional[str] = None, 
              prepend_lists: bool = False) -> None:
        """
        Apply a patch to the content at the specified path.
        
        Args:
            patch: Dict or List to merge with existing content
            path: JSONPath expression indicating where to apply the patch
            prepend_lists: If True, prepend items to lists instead of appending
            
        Raises:
            CompileError: If the JSONPath expression is invalid
            
        Examples:
            # Patch at root
            content.patch({"metadata": {"labels": {"app": "myapp"}}})
            
            # Patch at specific path
            content.patch({"app": "myapp"}, "$.metadata.labels")
            
            # Prepend to a list
            content.patch(["item1"], "$.spec.containers[0].args", prepend_lists=True)
        """
        # Handle patching at the root level
        if path is None:
            if isinstance(patch, dict):
                self.root.merge_update(Dict(patch), box_merge_lists="extend")
            elif isinstance(patch, list):
                if not hasattr(self.root, "extend"):
                    self.root = []
                self.root.extend(patch)
            return

        # Handle patching at a specific path
        try:
            # Parse the JSONPath expression
            jsonpath_expr = parse_jsonpath(path)
            matches = jsonpath_expr.find(self.root)

            if not matches:
                # Path doesn't exist yet - create it
                self._create_path_and_set_value(path, patch, prepend_lists)
            else:
                # Path exists - update existing values
                for match in matches:
                    self._update_match_with_patch(match, patch, jsonpath_expr, prepend_lists)
                    
        except JsonPathParserError as e:
            logger.error(f"Invalid JSONPath expression: {path}, error: {e}")
            raise CompileError(f"Invalid JSONPath expression: {path}")

    def _create_path_and_set_value(self, path: str, value: Any, prepend_lists: bool) -> None:
        """
        Create a path in the content and set a value at that path.
        
        Args:
            path: The path to create
            value: The value to set
            prepend_lists: Whether to prepend lists or not
        """
        # Parse path components (remove leading $ and .)
        path_parts = path.strip('$').strip('.').split('.')
        current = self.root

        # Navigate/create the path
        for part in path_parts[:-1]:
            # Handle array indexing
            if '[' in part:
                part_name, idx = part.split('[')
                idx = idx.rstrip(']')
                
                # Create the part if it doesn't exist
                if part_name not in current:
                    current[part_name] = []
                    
                # Make sure the array is long enough
                idx = int(idx)
                while len(current[part_name]) <= idx:
                    current[part_name].append({})
                    
                current = current[part_name][idx]
            else:
                if part not in current:
                    current[part] = {}
                current = current[part]

        # Set the final value
        last_part = path_parts[-1]
        if '[' in last_part:
            part_name, idx = last_part.split('[')
            idx = int(idx.rstrip(']'))
            
            if part_name not in current:
                current[part_name] = []
                
            while len(current[part_name]) <= idx:
                current[part_name].append({})
                
            if isinstance(value, dict):
                current[part_name][idx].update(value)
            elif isinstance(value, list):
                if prepend_lists:
                    current[part_name][idx][0:0] = value.copy()
                else:
                    current[part_name][idx].extend(value.copy())
            else:
                current[part_name][idx] = value
        else:
            if isinstance(value, dict):
                if last_part not in current:
                    current[last_part] = {}
                current[last_part].update(value)
            elif isinstance(value, list):
                if last_part not in current:
                    current[last_part] = []
                if prepend_lists:
                    current[last_part][0:0] = value.copy()
                else:
                    current[last_part].extend(value.copy())
            else:
                current[last_part] = value

    def _update_match_with_patch(self, match: JsonPathMatch, patch: Any, 
                               jsonpath_expr: Any, prepend_lists: bool) -> None:
        """
        Update a JSONPath match with the patch value.
        
        Args:
            match: The JSONPath match to update
            patch: The patch to apply
            jsonpath_expr: The JSONPath expression used to find the match
            prepend_lists: Whether to prepend lists or not
        """
        if isinstance(match.value, dict) and isinstance(patch, dict):
            # Merge dictionaries
            match.value.update(patch)
        elif isinstance(match.value, list):
            if isinstance(patch, list):
                # Extend or prepend lists
                if prepend_lists:
                    match.value[0:0] = patch  # Insert at beginning
                else:
                    match.value.extend(patch)
            else:
                # Append single item to list
                match.value.append(patch)
        else:
            # Replace value
            jsonpath_expr.update(self.root, patch)

    def regex_patch(self, patch: Dict[str, str]) -> None:
        """
        Apply regex-based patches to the content.
        
        This method finds string values at specified paths and applies regex replacements.
        
        Args:
            patch: Dictionary mapping JSONPath expressions to regex replacement pairs.
                   Each value is a string in the format 'regex_pattern::replacement'.
                   
        Example:
            ```python
            content.regex_patch({
                "$.metadata.name": "app-(.*)::service-\\1",
                "$.spec.template.spec.containers[0].image": "v1::v2"
            })
            ```
        """
        for path, pattern_replacement in patch.items():
            try:
                # Split the pattern and replacement
                if "::" not in pattern_replacement:
                    raise ValueError(f"Invalid pattern format, expected 'pattern::replacement': {pattern_replacement}")
                    
                pattern, replacement = pattern_replacement.split("::", 1)
                
                # Find the target value using JSONPath
                jsonpath_expr = parse_jsonpath(path)
                matches = jsonpath_expr.find(self.root)
                
                for match in matches:
                    if isinstance(match.value, str):
                        # Apply regex replacement
                        try:
                            new_value = re.sub(pattern, replacement, match.value)
                            jsonpath_expr.update(self.root, new_value)
                        except re.error as re_err:
                            logger.error(f"Invalid regex pattern '{pattern}': {re_err}")
                    else:
                        logger.warning(f"Cannot apply regex to non-string value at {path}: {match.value}")
            except (JsonPathParserError, ValueError, re.error) as e:
                logger.error(f"Error applying regex patch for {path}: {e}")

    def deep_merge(self, other: 'BaseContent') -> 'BaseContent':
        """
        Deeply merge another content object into this one.
        
        Args:
            other: Another BaseContent object to merge into this one
            
        Returns:
            Self, after the merge
            
        Example:
            ```python
            base_content = BaseContent.from_dict({"metadata": {"labels": {"app": "example"}}})
            additional = BaseContent.from_dict({"metadata": {"annotations": {"purpose": "test"}}})
            merged = base_content.deep_merge(additional)
            ```
        """
        if not isinstance(other, BaseContent):
            raise TypeError(f"Cannot merge object of type {type(other).__name__}")
            
        # Use patch to perform the deep merge
        self.patch(other.root)
        return self
        
    def to_yaml(self) -> str:
        """
        Convert the content to YAML format.
        
        Returns:
            YAML string representation of the content
        """
        return yaml.safe_dump(self.dump(), sort_keys=False)
        
    def to_dict(self) -> Dict:
        """
        Convert the content to a plain dictionary.
        
        Returns:
            Dictionary representation of the content
        """
        return self.dump()
        
    def __str__(self) -> str:
        """String representation of the content, useful for debugging."""
        kind = self.findpath(self.root, "kind", "Unknown")
        name = self.findpath(self.root, "metadata.name", "unnamed")
        return f"{kind}/{name} ({self.filename})"
        
    def __repr__(self) -> str:
        """Detailed representation of the content."""
        return f"<{self.__class__.__name__} {self.__str__()}>"