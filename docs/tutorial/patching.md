# Patching

## **Configuration Patching in Kapitan with `kgenlib`**

### **Automatic Configuration Patching**

`kgenlib` introduces a seamless way to auto-merge your configuration with default values using the `apply_patches` decorator attribute. This is especially handy when you want certain base configurations to be consistently present, and then layer on more specific configurations as needed.

### **Example: Merging with Defaults**

The following Python decorator showcases how you can employ the `apply_patches` feature:

```python
@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
    apply_patches=["generators.defaults.simple_fish_generator"],
)
```

In the above illustration:

- The `apply_patches` attribute is supplied with a list that denotes the path to the default configurations.
- The defined generator, when invoked, would incorporate configurations from `generators.defaults.simple_fish_generator` seamlessly into its own.

### **Advanced Features**

1. **Chaining Multiple Patches**: If there's a need to merge configurations from multiple sources, just extend the list provided to `apply_patches`.

2. **Variable Interpolation**: For those situations where you require custom configurations, `kgenlib` facilitates variable interpolation. This means you can use variables in your configuration and have them be replaced with actual values during the generation process.