import logging
import re
import string
from enum import StrEnum, auto

from kapitan.inputs.kadet import Dict, load_from_search_paths
from pydantic import field_validator

kgenlib = load_from_search_paths("kgenlib")
logger = logging.getLogger(__name__)

TERRAFORM_DISALLOWED_CHARS_REGEX = r"[^a-zA-Z\.\-\_\@]"


def cleanup_terraform_resource_id(resource_id: str) -> str:
    """
    Some characters can't be used inside of a terraform resource.
    This function helps with consistent removal and replacement of such chars.
    """
    return (
        re.sub(TERRAFORM_DISALLOWED_CHARS_REGEX, "", resource_id.split("/")[-1])
        .replace(".", "-")
        .replace("@", "_")
    )


class TerraformBlockTypes(StrEnum):
    BACKEND = auto()
    DATA = auto()
    IMPORT = auto()
    LOCALS = auto()
    MOVED = auto()
    OUTPUT = auto()
    PROVIDER = auto()
    REQUIRED_PROVIDERS = auto()
    RESOURCE = auto()
    TERRAFORM = auto()
    VARIABLE = auto()


class TerraformStore(kgenlib.BaseStore):
    filename: str = "output.tf.json"

    def dump(self, output_filename=None):
        """Return object dict/list."""
        for content in self.get_content_list():
            if output_filename:
                output_format = output_filename
            else:
                output_format = getattr(content, "filename", "output.tf.json")

            filename = output_format.format(content=content)
            self.root.setdefault(filename, Dict()).merge_update(
                content.root, box_merge_lists="extend"
            )

        return super().dump(already_processed=True)


class TerraformBlock(kgenlib.BaseContent):
    block_type: TerraformBlockTypes = TerraformBlockTypes.TERRAFORM
    type: str = None
    id: str
    defaults: dict = {}
    config: dict = {}

    @field_validator("id")
    @classmethod
    def name_must_valid_terraform_id(cls, v):
        allowed = set(string.ascii_letters + string.digits + "_-")
        if not set(v) <= allowed:
            raise ValueError(f"Invalid character in terraform id: {v}")
        return v

    def new(self):
        if self.type:
            self.filename = f"{self.type}.tf"
            self.provider = self.type.split("_")[0]
            self.patch_config(f"provider.{self.provider}.{self.block_type}")
        else:
            self.filename = f"{self.block_type}.tf"

        self.patch_config(f"{self.type}")

    def patch_config(self, inventory_path: str) -> None:
        """Apply patch to config"""
        patch = kgenlib.findpath(self.defaults, inventory_path, {})
        logger.debug(f"Applying patch {inventory_path} for {self.id}: {patch}")
        kgenlib.merge(patch, self.config)

    @property
    def resource(self):
        if self.type:
            return self.root[self.block_type][self.type].setdefault(self.id, {})
        else:
            return self.root[self.block_type].setdefault(self.id, {})

    @resource.setter
    def resource(self, value):
        self.add(value)

    def set(self, config=None):
        config = config or self.config
        self.root[self.block_type][self.type].setdefault(self.id, config).update(config)

    def add(self, name, value):
        self.root[self.block_type][self.type].setdefault(self.id, {})[name] = value

    def get_reference(
        self, attr: str = None, wrap: bool = True, prefix: str = "", filter: str = None
    ) -> str:
        """Get reference or attribute reference for terraform resource

        Args:
            attr (str, optional): The attribute to get. Defaults to None.
            wrap (bool, optional): Whether to wrap the result. Defaults to True.
            prefix (str, optional): Whether to prefix the result. Defaults to "".

        Raises:
            TypeError: Unknown block_type

        Returns:
            str: a reference or attribute reference for terraform, e.g. "${var.foo}"
        """

        if self.block_type in (TerraformBlockTypes.DATA):
            reference = f"data.{self.type}.{self.id}"
        elif self.block_type in (TerraformBlockTypes.RESOURCE):
            reference = f"{prefix}{self.type}.{self.id}"
        elif self.block_type in (
            TerraformBlockTypes.OUTPUT,
            TerraformBlockTypes.VARIABLE,
            TerraformBlockTypes.LOCALS,
        ):
            reference = f"{prefix}{self.id}"
        else:
            raise TypeError(
                f"Cannot produced wrapped reference for block_type={self.block_type}"
            )

        if filter:
            reference = f"{reference}[{filter}]"

        if attr:
            reference = f"{reference}.{attr}"

        if wrap:
            return f"${{{reference}}}"
        else:
            return reference


class TerraformResource(TerraformBlock):
    block_type: TerraformBlockTypes = TerraformBlockTypes.RESOURCE

    def body(self):
        # We pop/purge them because these are internal kapitan instructions
        self.moved_from(self.config.pop("moved_from", None))
        self.import_from(self.config.pop("import_from", None))

        super().body()

    def import_from(self, import_id: str = None):
        if import_id:
            import_config = {"to": self.get_reference(wrap=False), "id": import_id}
            self.root.setdefault("import", []).append(import_config)

    def moved_from(self, old_id: str = None):
        if old_id:
            moved_config = {
                "to": self.get_reference(wrap=False),
                "from": f"{self.type}.{old_id}",
            }
            self.root.setdefault("moved", []).append(moved_config)


class TerraformLocal(TerraformBlock):
    block_type: TerraformBlockTypes = TerraformBlockTypes.LOCALS

    def set_local(self, name, value):
        self.root.locals.setdefault(name, value)

    def body(self):
        if self.config:
            config = self.config
            name = config.get("name", self.id)
            value = config.get("value", None)
            if value:
                self.set_local(name, value)


class TerraformData(TerraformBlock):
    block_type: TerraformBlockTypes = TerraformBlockTypes.DATA

    def body(self):
        config = self.config
        name = config.get("name", self.id)
        value = config.get("value")
        self.root.data.setdefault(name, value)


class TerraformProvider(TerraformBlock):
    block_type: TerraformBlockTypes = TerraformBlockTypes.PROVIDER

    def add(self, name, value):
        self.root.setdefault(self.block_type, {}).setdefault(name, value)[name] = value

    def set(self, config=None):
        if config is None:
            config = self.config
        self.root.setdefault(self.block_type, {}).setdefault(self.id, config).update(
            config
        )
