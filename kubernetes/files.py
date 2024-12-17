import logging

from .common import kgenlib

logger = logging.getLogger(__name__)


@kgenlib.register_generator(path="generators.kubernetes.raw")
class RawManifestFilesGenerator(kgenlib.BaseStore):
    def body(self):
        for file in self.config.files:
            self.add(kgenlib.BaseStore.from_yaml_file(file))
        if self.config.filename:
            [
                setattr(content, "filename", self.config.filename)
                for content in self.content_list
            ]
