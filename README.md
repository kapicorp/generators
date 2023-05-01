# **`Kapitan`** **Generators**

This repository contains the current effors in creating **`Kapitan`** **Generators**

This are meant to be used as part of the **`Kapitan `** project and not on their own. 
Please see <kapitan.dev> or <https://github.com/kapicorp/kapitan-reference> to get started.

## What are **Generators**

As explained in the blog post [Keep your ship together with Kapitan](https://medium.com/kapitan-blog/keep-your-ship-together-with-kapitan-d82d441cc3e7), (**`Kapitan`**) generators are a
powerful idea to simplify the management your configuration setup.

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

## **Kapicorp Generators**

| Name | Description | Documentation |
| ---- | ----------- | -------------- |
| [documentation](documentation) | Documentation generator | [Documentation](../documentation/README.md)
| [ingresses](ingresses) | Kubernetes Ingress generator | [Documentation](../ingresses/README.md)
| [kubernetes](kubernetes) | Kubernetes resources generator | [Documentation](../kubernetes/README.md)|
| [terraform](terraform) | Terraform generator | [Documentation](../terraform/README.md)
## Community

### Generators by [neXenio](https://www.nexenio.com/)

| Name | Description | Documentation |
| ---- | ----------- | -------------- |
| [rabbitmq](rabbitmq) | Manifests generator for RabbitMQ| TBD |
| [argocd](argocd) | Manifests generator for ArgoCD | TBD |
