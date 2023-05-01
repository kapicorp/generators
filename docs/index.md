# **`Kapitan`** **Generators**

## What are **Generators**

**`Kapitan`** generators are a
powerful addon to **`Kapitan`** to simplify the management your configuration setup.

Think of them like "Universal Templates" that you can use to quickly create configurations (for instance, Kubernetes resources) through a Domain-Specific configuration.

For example, the configuration:

```yaml
parameters:
  components:
    nginx:
      image: nginx
```

Instructs the "***Kubernetes Generator***" to create a `Deployment` kubernete resoures for nginx. The configuration can be extended to include Secrets, Config Maps, Services, env variables, ports and more. 

The same configuration can be used by a "***Documentation Generator***" to create a `nginx.md` file with a description of the configuration to be consumed as documentation.