"""
kgenlib - Generator library for Kubernetes manifests
"""

import logging
from kapitan.inputs.kadet import current_target, inventory_global

# Import and expose key components
from .contexts import generator_context, target_context, error_handling, batch_processing
from .exceptions import DeleteContent
from .generators import (
    register_generator,
    register_function,
    get_generators_for_target,
    expand_and_run,  # This should match the function name in generators.py
    GeneratorClass,
    load_generators,
    get_generator_class
)
from .interfaces import ContentMixin, ResourceCollection
from .models import (
    GeneratorParams,
    GeneratorFunctionParams,
    ContentMutateSpec,
    ContentType,
    BaseModel,
)
from .content import BaseContent
from .base import (
    BaseGenerator,
    BaseStore
)
from .utils import (
    render_jinja,
    render_json,
    render_yaml,
    findpath,
    merge,
    patch_config
)


# Set up logging
logger = logging.getLogger(__name__)

# Export target reference for convenience - handle missing context case
try:
    target = current_target.get()
except LookupError:
    logger.debug("No current target context found, using default")
    target = "default_target"

# Define what should be imported with "from kgenlib import *"
__all__ = [
    'BaseContent',
    'BaseGenerator',
    'BaseStore',
    'ContentMixin',
    'ContentMutateSpec',
    'ContentType',
    'DeleteContent',
    'GeneratorClass',
    'GeneratorFunctionParams',
    'GeneratorParams',
    'ResourceCollection',
    'batch_processing',
    'error_handling',
    'expand_and_run',
    'findpath',
    'generator_context',
    'load_generators',
    'merge',
    'patch_config',
    'register_generator',
    'render_jinja',
    'render_json',
    'render_yaml',
    'target',
    'target_context'
]