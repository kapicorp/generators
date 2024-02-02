# **`Kapitan`** **Generators**

This repository contains the current efforts in creating **`Kapitan`** **Generators**.

These are meant to be used as part of the **`Kapitan`** project and not on their own.
Please see <kapitan.dev> or <https://github.com/kapicorp/kapitan-reference> to get started.

## What are **Generators**

As explained in the blog post [Keep your ship together with Kapitan](https://medium.com/kapitan-blog/keep-your-ship-together-with-kapitan-d82d441cc3e7), (**`Kapitan`**) generators are a
powerful idea to simplify the management your configuration setup.

Think of them as universal templates that you can use to quickly create configurations (for instance, Kubernetes resources) through a domain-specific configuration.

For example, the configuration:

```yaml
parameters:
  components:
    nginx:
      image: nginx
```

Instructs the "***Kubernetes Generator***" to create a `Deployment` Kubernetes resource for nginx. The configuration can be extended to include Secrets, ConfigMaps, Services, env variables, ports and more.

The same configuration can be used by a "***Documentation Generator***" to create an `nginx.md` file with a description of the configuration to be consumed as documentation.

## **Kapicorp Generators**

| Name                           | Description                    | Documentation                               |
|--------------------------------|--------------------------------|---------------------------------------------|
| [documentation](documentation) | Documentation generator        | [Documentation](../documentation/README.md) |
| [kubernetes](kubernetes)       | Kubernetes resources generator | [Documentation](../kubernetes/README.md)    |
| [terraform](terraform)         | Terraform generator            | [Documentation](../terraform/README.md)     |