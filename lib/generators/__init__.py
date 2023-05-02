import functools
from types import FunctionType
from typing import List

import yaml
from box.box_list import BoxList
from box.exceptions import BoxValueError
from kapitan.cached import args
from kapitan.inputs.helm import HelmChart
from kapitan.inputs.kadet import BaseModel, CompileError, Dict, inventory
from kapitan.utils import render_jinja2_file

inventory = inventory(lazy=True)
search_paths = args.get("search_paths")


def merge(source, destination):
    """Merge source into destination"""
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, value)
            if node is None:
                destination[key] = value
            else:
                merge(value, node)
        else:
            destination[key] = destination.setdefault(key, value)

    return destination


def render_jinja(filename, ctx):
    """Render jinja2 template with ctx"""
    return render_jinja2_file(filename, ctx, search_paths=search_paths)


def findpath(obj, path, default=None):
    """Find path in obj, return default if not found"""
    path_parts = path.split(".")
    try:
        value = getattr(obj, path_parts[0])
    except KeyError as e:
        if default is not None:
            return default
        raise CompileError(f"Key {e} not found in {obj}")

    if len(path_parts) == 1:
        return value
    else:
        return findpath(value, ".".join(path_parts[1:]))


def patch_config(config, paths):
    """Patch config with patches from inventory paths"""
    patched_config = Dict(config)
    patches_applied = []
    for path in paths:
        try:
            path = path.format(**config)
        except KeyError:
            # Silently ignore missing keys
            continue
        patch = findpath(inventory.parameters, path, {})
        patches_applied.append(patch)

        patched_config = merge(patch, patched_config)
    return patched_config, patches_applied


def register_generator(*args, **kwargs):
    """Register a generator function"""

    def wrapper(func):
        @functools.wraps(func)
        def wrapped_func():
            configs = findpath(inventory.parameters, kwargs.get("path"))

            results = []
            for name, config in configs.items():
                patched_config, patches = patch_config(
                    config, kwargs.get("apply_patches", [])
                )

                output = func(
                    name=name,
                    config=patched_config,
                    patches_applied=patches,
                    original_config=config,
                    **kwargs,
                )

                if isinstance(output.root, list):
                    results.extend(output.root)
                else:
                    results.append(output)
            return results

        Generator.register_function(wrapped_func)
        return wrapped_func

    return wrapper


class Generator:
    inventory: Dict
    functions: List[FunctionType] = []

    @classmethod
    def generate(cls):
        results = []
        for func in cls.functions:
            results.extend(func())
        return results

    @classmethod
    def register_function(cls, func):
        Generator.functions.append(func)


class BaseResource(BaseModel):
    kind: str  # Required
    api_version: str  # Required
    name: str  # Required

    @property
    def bundle(self):
        return f"{self.kind.lower()}-{self.name}"

    @classmethod
    def from_baseobj(cls, baseobj):
        """Return a KubernetesResource initialised with baseobj."""
        return cls.from_dict(baseobj.root)

    @classmethod
    def from_yaml_multidoc(cls, file_path):
        """Return list generator of KubernetesResource initialised with file_path data."""
        with open(file_path) as fp:
            yaml_objs = yaml.safe_load_all(fp)
            for yaml_obj in yaml_objs:
                if yaml_obj:
                    try:
                        yield cls.from_dict(yaml_obj)
                    except BoxValueError as e:
                        raise CompileError(
                            f"error when importing item '{yaml_obj}' for file {file_path}: {e}"
                        )

    @classmethod
    def from_dict(cls, dict_value):
        """Return a KubernetesResource initialise with dict_value."""

        if dict_value:
            try:
                resource = Dict(dict_value)
            except BoxValueError as e:
                raise CompileError(
                    f"error when importing item '{dict_value}' of type {type(dict_value)}: {e}"
                )

            name = resource.metadata.name
            api_version = resource.apiVersion
            kind = resource.kind

            bobj = cls(name=name, api_version=api_version, kind=kind)
            bobj.root = resource
            return bobj
        else:
            return None

    def findpath(self, obj, path):
        path_parts = path.split(".")
        value = getattr(obj, path_parts[0])
        if len(path_parts) == 1:
            return value
        else:
            return self.findpath(value, ".".join(path_parts[1:]))

    def mutate(self, mutations):
        for mutation in mutations:
            if "patch" in mutation:
                if self.match(mutation["condition"]):
                    self.patch(mutation["patch"])
            elif "delete" in mutation:
                if self.match(mutation["condition"]):
                    self = None

    def match(self, match_conditions):
        for key, values in match_conditions.items():
            value = self.findpath(self.root, key)
            if value in values:
                continue
            else:
                return False
        return True

    def patch(self, yaml):
        self.root.merge_update(Dict(yaml))


class BaseResourcesStore(BaseModel):
    bundles: dict = {
        "Secret": "secrets",
        "ConfigMap": "configmaps",
        "Service": "services",
    }
    default_bundle: str = "{resource.bundle}"
    resources: List[BaseResource] = []

    def add_from_yaml(self, file_path):
        resources = list(BaseResource.from_yaml_multidoc(file_path))
        self.add_list(resources)

    def add_from_dict(self, dict_value: dict):
        resource = BaseResource.from_dict(dict_value)
        self.add(resource)

    def add_from_helm_chart(self, **kwargs):
        self.add_list(
            [
                BaseResource.from_baseobj(resource)
                for resource in HelmChart(**kwargs).root.values()
            ]
        )

    def add_from_single_baseobg(self, baseobj):
        self.add(BaseResource.from_baseobj(baseobj))

    def add_from_baseobj_list(self, baseobj_list):
        for resource in baseobj_list:
            if isinstance(resource, BoxList) or isinstance(resource, list):
                for r in resource:
                    self.add(BaseResource.from_dict(r))
            else:
                self.add(BaseResource.from_baseobj(resource))

    def add_list(self, resources: List[BaseResource]):
        for resource in resources:
            self.add(resource)

    def add(self, resource: BaseResource):
        if resource:
            resource.bundle = self.bundles.get(resource.kind, resource.bundle)
            self.resources.append(resource)

    def patch_all_resources(self, patch: Dict):
        for resource in self.get_all_resources():
            resource.patch(patch)

    def mutate_all_resources(self, mutations: List):
        for resource in self.get_all_resources():
            resource.mutate(mutations)

    def get_all_resources(self):
        for resource in self.resources:
            yield resource

    def dump(self, output_filename=None):
        """Return object dict/list."""

        for resource in self.resources:
            if output_filename:
                output_format = output_filename
            else:
                output_format = self.bundles.get(resource.kind, self.default_bundle)

            filename = output_format.format(resource=resource)
            self.root.setdefault(filename, []).append(resource)
        return super().dump()
