# Target generators

## **Target Generators in Kapitan**

### **What is a Target Generator?**

A target generator is a specialized Generator class that focuses on processing the configuration of a single target. To give an illustrative example, if one sets up the configuration for a target named `nginx` as follows:

```yaml
parameters:
  components:
    nginx:
      image: nginx
      ...
```

The expected behavior would be for the `kubernetes` generator to churn out manifests into the `compiled/nginx/manifest` output target. What's noteworthy here is that the nature of resources generated—like ConfigMap, Secret, Service—depends on the `nginx` component's configuration.

### **Crafting a Target Generator**

To lay the foundation for a target generator, employ the provided Python decorator:

```python
@kgenlib.register_generator(
    path="components",
    ...
)
class Components(kgenlib.BaseStore):
```

This configuration indicates that the generator will spring into action for configurations housed under the `parameters.components` inventory segment, but only for that specific target.
