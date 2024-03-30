import base64
import hashlib
import logging
import os

import yaml
from kapitan.inputs.kadet import Dict

from .common import KubernetesResource, ConfigDataSpec, kgenlib, SharedConfigSpec, SecretSpec, ConfigMapSpec

logger = logging.getLogger(__name__)


class SharedConfig(KubernetesResource):
    """Shared base class for both ConfigMap and Secret components."""

    config: SharedConfigSpec

    @staticmethod
    def encode_string(unencoded_string):
        """Encode a string using base64."""
        return base64.b64encode(unencoded_string.encode("ascii")).decode("ascii")

    def setup_metadata(self):
        """Set up metadata like namespace, annotations, and labels."""
        self.items = self.config.items
        logger.debug(f"Set up metadata for {self.name}.")

    def add_directory(self, directory, encode=False, stringdata=False):
        """Add contents of files in a directory."""
        if directory and os.path.isdir(directory):
            logger.debug(f"Adding files from directory {directory} to {self.name}.")
            for filename in os.listdir(directory):
                with open(f"{directory}/{filename}", "r") as f:
                    file_content = f.read()
                    self.add_item(
                        filename,
                        file_content,
                        request_encode=encode,
                        stringdata=stringdata,
                    )

    def add_item(self, key, value, request_encode=False, stringdata=False):
        """Add a single item to the resource."""
        encode = not stringdata and request_encode
        field = "stringData" if stringdata else "data"
        self.root[field][key] = self.encode_string(value) if encode else value
        logger.debug(f"Added item with key '{key}' to {self.name}.")

    def add_from_spec(self, key, spec: ConfigDataSpec, stringdata=False):
        """Add data from a specification dictionary."""
        logger.debug(f"Adding item from spec {spec} to {self.name}.")
        encode = spec.b64_encode
        value = None
        
        if spec.value:
            value = spec.value
        elif spec.value_as_str:
            value = yaml.dump(
                spec.value_as_str.dump(),
                default_flow_style=False,
                width=1000,
            )
        elif spec.template:
            value = kgenlib.render_jinja(spec.template, spec.values)
        elif spec.file:
            with open(spec.file, "r") as f:
                value = f.read()

        if value:
            self.add_item(key, value, request_encode=encode, stringdata=stringdata)

    def versioning(self):
        import json

        """Handle versioning for the resource."""
        if self.config.versioned:
            keys_of_interest = ["data", "binaryData", "stringData"]
            subset = {
                key: value
                for key, value in self.root.to_dict().items()
                if key in keys_of_interest
            }

            # Create a sorted representation for the subset
            canonical_representation = json.dumps(subset, sort_keys=True)

            self.hash = hashlib.sha256(canonical_representation.encode()).hexdigest()[
                :8
            ]

            self.rendered_name = f"{self.name}-{self.hash}"
            self.root.metadata.name = self.rendered_name
            logger.debug(f"Versioning enabled for {self.name}. Using hash {self.hash}.")

    def body(self):
        """Shared logic for building the body of both Secret and ConfigMap."""
        logger.debug(f"Building body for {self.name}.")
        super().body()
        self.setup_metadata()

        if getattr(self, "workload", None) and self.workload.root.metadata.name:
            self.add_label("name", self.workload.root.metadata.name)

        for key, spec in self.config.data.items():
            self.add_from_spec(key, spec)

        self.add_directory(self.config.directory)
        self.post_setup()
        self.versioning()
        if getattr(self, "workload", None):
            self.workload.add_volumes_for_object(self)

    def post_setup(self):
        """Method to be overridden in derived classes for extra setups."""
        pass


class ComponentConfig(SharedConfig):
    """Specific implementation of ConfigMap."""

    kind: str = "ConfigMap"
    api_version: str = "v1"
    config: ConfigMapSpec


class ComponentSecret(SharedConfig):
    """Specific implementation of Secret."""

    kind: str = "Secret"
    api_version: str = "v1"
    config: SecretSpec

    def post_setup(self):
        """Specific setups for the Secret."""
        self.root.type = self.config.type
        logger.debug(f"Setting Secret type for {self.name} as {self.root.type}.")
        for spec in self.config.string_data:
            self.add_from_spec(spec, stringdata=True)
        self.add_directory(self.config.directory, encode=True)


@kgenlib.register_generator(
    path="generators.kubernetes.secrets",
    apply_patches=["generators.manifest.default_resource"],
)
class SecretGenerator(kgenlib.BaseStore):
    def body(self):
        logger.debug(f"Generating Secret for {self.name}.")
        namespace = self.config.get(
            "namespace", self.inventory.parameters.get("namespace", None)
        )
        self.add(
            ComponentSecret(name=self.name, config=self.config, namespace=namespace)
        )


@kgenlib.register_generator(
    path="generators.kubernetes.config_maps",
    apply_patches=["generators.manifest.default_resource"],
)
class ConfigGenerator(kgenlib.BaseStore):
    def body(self):
        logger.debug(f"Generating ConfigMap for {self.name}.")
        namespace = self.config.get(
            "namespace", self.inventory.parameters.get("namespace", None)
        )
        self.add(
            ComponentConfig(name=self.name, config=self.config, namespace=namespace)
        )
