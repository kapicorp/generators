# Example code

## `GenSimpleFishGenerator`

1. Create a new file named `fish.py` in the directory `system/generators/kubernetes/` and add the following content:

    ```python
    import logging
    logger = logging.getLogger(__name__)

    from .common import KubernetesResource, kgenlib
    ...
    ```


1. Register the generator classes with Kapitan using the `@kgenlib.register_generator` annotation. Here's an example:

    ```python
    @kgenlib.register_generator(
        path="kapicorp.simple_fish_generator",
    )
    class GenSimpleFishGenerator(KubernetesResource):
      api_version = "fish/v1"
      kind = "Fish"

      def body(self):
        super().body()
        logger.info(f"Running {__name__} with id = {self.id} and config = {self.config}")
    ```

    When Kapitan runs, it matches dictionary items with the specified path, then invokes your `GenSimpleFishGenerator` class.

1. Execute Kapitan to see the generated output:
    ```bash
    ./kapitan compile -t tutorial
    ```

1. Inspect the generated files:
    ```bash
    git status compiled
    ```

## Enhancing the Resource

Utilize the `self.config` variable to enrich the fish object:

```python
    ...
    @kgenlib.register_generator(
        path="kapicorp.simple_fish_generator",
    )
    ...
    self.root.spec.family = self.config.get("family", None)
```

This addition will populate the `family` attribute of the fish under the `spec` field.