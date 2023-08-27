# Global Generators

## **Global Generators in Kapitan**

### **Introduction to Global Generators**

Unlike target generators, which derive their configurations from a specific target inventory, global generators cater to situations where configurations span multiple 'source' targets. Yet, there's a requirement for their outputs to funnel into a singular 'destination' target.

### **Use Case Example**

Consider generating ArgoCD Applications. While the manifest files need generation into the "apps_of_apps" target, it's ideal for the configurations to reside alongside the source target.

### **Crafting a Global Generator**

To initiate a global generator, employ the Python decorator below:

```python
@kgenlib.register_generator(
    path="generators.argocd.applications",
    global_generator=True,
    activation_path="argocd.app_of_apps",
)
class GenArgoCDApplication(kgenlib.BaseStore):
  ...
```

In the above snippet:

- **`global_generator`**: Ensures configurations are sourced from all clusters, not just one.
- **`activation_path`**: Informs Kapitan to generate manifests within the target housing that unique path.
