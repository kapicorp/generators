"""
Data models for the kgenlib package.

This module defines the Pydantic models used throughout kgenlib for:
- Generator configuration
- Content mutation specifications
- Type definitions and constants
"""

from enum import Enum, auto
from typing import Annotated, Dict, List, Optional, Union, Any, ClassVar

import pydantic
from pydantic import (
    BaseModel, Field, field_validator, model_validator,
    ValidationInfo
)


# Constants for reuse
class ContentTypeValues(str, Enum):
    """String constants for content type values."""
    YAML = "yaml"
    JSON = "json"
    RAW = "raw"


class MutationActions(str, Enum):
    """String constants for mutation action types."""
    PATCH = "patch"
    REGEX_PATCH = "regex_patch"
    BUNDLE = "bundle"
    DELETE = "delete"
    PRUNE = "prune"


# Type aliases for better code readability
MutationCondition = Annotated[
    Dict[str, List[str]],
    "A dictionary mapping JSONPath expressions to lists of values that must match",
]

PatchValue = Union[Dict[str, Any], List[Any]]
RegexPattern = str  # In format "pattern::replacement"


class GeneratorParams(BaseModel):
    """
    Represents parameters for a generator function.

    Attributes:
        path: The JMESPath expression to locate configurations in the inventory.
        apply_patches: A list of JMESPath expressions for patches.
        global_generator: Whether the generator applies globally to all inventories.
        activation_path: JMESPath expression that activates the global generator.
    """
    path: str
    apply_patches: List[str] = Field(default_factory=list)
    global_generator: bool = False
    activation_path: Optional[str] = None

    @field_validator('path')
    def path_must_not_be_empty(cls, v):
        """Validate that path is not empty."""
        if not v:
            raise ValueError("path must not be empty")
        return v

    @field_validator('apply_patches')
    def patch_paths_must_not_be_empty(cls, values):
        """Validate that each patch path is not empty."""
        for v in values:
            if not v:
                raise ValueError("patch paths must not be empty")
        return values

    class Config:
        """Pydantic configuration."""
        model_config = {
            "frozen": False,  # Allow modification after creation
            "extra": "ignore",  # Ignore extra attributes
            "validate_assignment": True,  # Validate attributes on assignment
        }


class GeneratorFunctionParams(BaseModel):
    """
    Represents parameters for a generator function.
    """
    target: str
    id: str
    name: str
    config: Dict[str, Any]
    function: str
    params: GeneratorParams
    defaults: Dict[str, Any]
    inventory: Dict[str, Any]
    global_inventory: Dict[str, Any]

    @field_validator('target', 'id', 'name', 'function')
    def validate_string_fields(cls, v, info: ValidationInfo):
        """Validate that string fields are not empty."""
        if not v:
            raise ValueError(f"{info.field_name} must not be empty")
        return v

    def get_merged_config(self) -> Dict[str, Any]:
        """
        Get a configuration dictionary with defaults applied.
        
        Returns:
            A dictionary with defaults applied to the configuration
        """
        merged = self.defaults.copy()
        merged.update(self.config)
        return merged

    class Config:
        """Pydantic configuration."""
        model_config = {
            "frozen": False,
            "validate_assignment": True,
            "arbitrary_types_allowed": True,
        }


class RegExpMatchMutationSpec(BaseModel):
    """
    Specification for regular expression-based mutation.
    """
    patch: Dict[str, str]
    conditions: MutationCondition

    @field_validator('patch')
    def validate_regex_patterns(cls, v):
        """Validate that each regex pattern includes the '::' separator."""
        for path, pattern in v.items():
            if '::' not in pattern:
                raise ValueError(f"Regex pattern for path '{path}' must include '::' separator")
        return v


class PatchMutationSpec(BaseModel):
    """
    Specification for patch-based mutation.
    """
    patch: PatchValue
    conditions: MutationCondition
    path: Optional[str] = None
    prepend_lists: bool = False

    @model_validator(mode='after')
    def validate_patch_structure(self):
        """Validate that patch and path are compatible."""
        if self.path and not isinstance(self.patch, (dict, list)):
            raise ValueError(f"When path is specified, patch must be a dict or list, got {type(self.patch).__name__}")
        return self


class BundleMutationSpec(BaseModel):
    """
    Specification for bundle-based mutation.
    """
    filename: str
    conditions: MutationCondition
    break_: bool = Field(default=True, alias="break")

    @field_validator('filename')
    def validate_filename(cls, v):
        """Validate that filename is not empty."""
        if not v:
            raise ValueError("filename must not be empty")
        return v

    class Config:
        """Pydantic configuration."""
        model_config = {
            "validate_by_name": True,  # Updated from allow_population_by_field_name
        }


class DeleteMutationSpec(BaseModel):
    """
    Specification for delete-based mutation.
    """
    conditions: MutationCondition


class PruneMutationSpec(BaseModel):
    """
    Specification for prune-based mutation.
    """
    prune: bool = True
    conditions: MutationCondition
    break_: bool = Field(default=True, alias="break")

    class Config:
        """Pydantic configuration."""
        model_config = {
            "validate_by_name": True,  # Updated from allow_population_by_field_name
        }


class ContentMutateSpec(BaseModel):
    """
    Complete specification for content mutation.
    """
    regex_patch: List[RegExpMatchMutationSpec] = Field(default_factory=list)
    patch: List[PatchMutationSpec] = Field(default_factory=list)
    bundle: List[BundleMutationSpec] = Field(default_factory=list)  # Fixed typo: .list -> =list
    delete: List[DeleteMutationSpec] = Field(default_factory=list)
    prune: List[PruneMutationSpec] = Field(default_factory=list)
    
    def has_mutations(self) -> bool:
        """
        Check if this spec contains any mutations.
        
        Returns:
            True if there are any mutations defined, False otherwise
        """
        return any([
            self.regex_patch,
            self.patch,
            self.bundle,
            self.delete,
            self.prune
        ])
    
    def count_mutations(self) -> int:
        """
        Count the total number of mutations in this spec.
        
        Returns:
            Total number of mutations across all types
        """
        return sum([
            len(self.regex_patch),
            len(self.patch),
            len(self.bundle),
            len(self.delete),
            len(self.prune)
        ])
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentMutateSpec':
        """
        Create a ContentMutateSpec from a dictionary.
        
        This is a convenience method to create a spec from a dictionary
        while handling validation errors.
        
        Args:
            data: Dictionary containing mutation specifications
            
        Returns:
            A new ContentMutateSpec instance
            
        Raises:
            ValueError: If the data is invalid
        """
        try:
            return cls.model_validate(data)
        except pydantic.ValidationError as e:
            raise ValueError(f"Invalid mutation spec: {e}")


class ContentType(Enum):
    """
    Enumeration of content types.
    """
    YAML = ContentTypeValues.YAML
    JSON = ContentTypeValues.JSON
    RAW = ContentTypeValues.RAW
    
    @classmethod
    def from_string(cls, value: str) -> 'ContentType':
        """
        Create a ContentType enum from a string value.
        """
        try:
            return cls(ContentTypeValues(value.lower()))
        except ValueError:
            valid_values = ", ".join(e.value for e in ContentTypeValues)
            raise ValueError(f"Invalid content type: '{value}'. Must be one of: {valid_values}")


# Re-export key types for convenience
PatchAction = PatchMutationSpec
RegexPatchAction = RegExpMatchMutationSpec 
DeleteAction = DeleteMutationSpec
PruneAction = PruneMutationSpec
BundleAction = BundleMutationSpec