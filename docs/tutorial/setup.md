# Setup

Developing new generators is straightforward with the kgenlib library. In this tutorial, you'll learn to create a generator class for the Kubernetes CRD object, the `Fish CRD`.

## Setup the Environment

1. Clone the Kapitan Reference repository:
    ```bash
    git clone git@github.com:kapicorp/kapitan-reference.git
    cd kapitan-reference
    ```

2. Verify the setup by compiling:
    ```bash
    ./kapitan compile
    ```

## Configuration
Kapitan should iterate over the following configuration to produce Kubernetes resources:

```yaml
parameters:
  kapicorp:
    simple_fish_generator:
      cod:
        family: Gadidae
      blue_shark:
        name: blue-shark
        family: Carcharhinidae
```
> **Note**: This configuration is available in `targets/examples/tutorial.yml`.