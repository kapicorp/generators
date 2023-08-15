# Tutorial

Developing new generators is very easy, thanks to our library [kgenlib](/lib/kgenlib)

In this tutorial we will learn how to create a small generator class for to generate a new Kubernetes CRD object, the `Fish CRD`

We want Kapitan to iterate over the following configuration and produce some Kubernetes resources for us.

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

You will find this configuration already available in the `targets/examples/tutorial.yml` target file.

## Setup the environment

Please clone the Kapitan Reference repository and check that you can compile by running:

```shell
git clone git@github.com:kapicorp/kapitan-reference.git
cd kapitan-reference

./kapitan compile
```

```
Compiled postgres-proxy (1.51s)
Compiled tesoro (1.70s)
Compiled echo-server (1.64s)
Compiled mysql (1.67s)
Compiled gke-pvm-killer (1.17s)
Compiled prod-sockshop (4.74s)
Compiled dev-sockshop (4.74s)
Compiled tutorial (1.68s)
Compiled global (0.76s)
Compiled examples (2.60s)
Compiled pritunl (2.03s)
Compiled sock-shop (4.36s)
```

## Create the generator python module file

Let's create a new file `fish.py` under the kubernetes generator folder `system/generators/kubernetes/` with the following boilerplate

```py
import logging

logger = logging.getLogger(__name__)

from .common import KubernetesResource, kgenlib
```

## Import the module in the main generator class

Additionally, we need to import the generator in the `system/generators/kubernetes/__init__.py`  file:

```py

...
from .fish import *
...

```

## Register your generator classes

The library provides a simple Python annotation that registers your generator with Kapitan.

For instance, the following annotation will register the class to react to the path specified.

```py
...

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


!!! info "How does it work?" 
      When `Kapitan` runs, it will find all the items in dictionary matching the path (`kapicorp.simple_fish_generator`), and will call your `GenSimpleFishGenerator` class passing the items alongside some other context variables.
      As you can see we are using the `KubernetesResource` class, which will create a file with some basic content for us.

Now run `kapitan` to see the output

```bash
./kapitan compile -t tutorial
Rendered inventory (1.70s)
Running kadet_component_kubernetes.fish with id = cod and config = {'family': 'Gadidae'}
Running kadet_component_kubernetes.fish with id = blue_shark and config = {'name': 'blue-shark', 'family': 'Carcharhinidae'}
Compiled tutorial (0.24s)
```

--- 

Also look at the produced files

```bash
git status compiled
...
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        compiled/tutorial/manifests/blue-shark-bundle.yml
        compiled/tutorial/manifests/cod-bundle.yml
```

```yaml
apiVersion: fish/v1
kind: Fish
metadata:
  labels:
    name: blue-shark
  name: blue-shark
```

## Building the resource

The generator will make available for you some context variables that you can use to access more configs and build the object you want.

Let's use the `self.config` to add the `family` of the fish to the `spec` field:

```py
...

@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
)
class GenSimpleFishGenerator(KubernetesResource):
  api_version = "fish/v1"
  kind = "Fish"

  def body(self):
    super().body()
    logger.info(f"Running {__name__} with id = {self.id} and config = {self.config}")
    self.root.spec.family = self.config.get("family", None)
```

Which produces

```yaml
apiVersion: fish/v1
kind: Fish
metadata:
  labels:
    name: blue-shark
  name: blue-shark
spec:
  family: Carcharhinidae
```

## Patching configs

The generators support automatic patching of configs by using the `apply_patches` decorator attribute.

For instance, let's imagine that we want to merge the following configuration with all types of `Fish` resources:

```yaml
parameters:
  generators:
    defaults:
      simple_fish_generator:
        habitat: water
```

We can then simply call the decorator with the following configuration:

```py
@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
    apply_patches=["generators.defaults.simple_fish_generator"],
)
class GenSimpleFishGenerator(KubernetesResource):
  api_version = "fish/v1"
  kind = "Fish"

  def body(self):
    super().body()
    logger.info(f"Running {__name__} with id = {self.id} and config = {self.config}")
    self.root.spec.family = self.config.get("family", None)
```

We then get `{'habitat': 'water'}` automatically added to our dictionary

```shell
./kapitan compile -t tutorial
Rendered inventory (1.70s)
Running kadet_component_kubernetes.fish with id = cod and config = {'family': 'Gadidae', 'habitat': 'water'}
Running kadet_component_kubernetes.fish with id = blue_shark and config = {'name': 'blue-shark', 'family': 'Carcharhinidae', 'habitat': 'water'}
Compiled tutorial (0.24s)

```

We can also chain together patches, and use variable interpolation to apply for instance some defaults only for some specific objects:

```py

@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
    apply_patches=[
      "generators.defaults.simple_fish_generator"
      "generators.defaults.{habitat}
      ],
)
```

will patch the following configuration if `habitat`` is "water":

```yaml
parameters:
  generators:
    defaults:
      water:
        fins: yes
```

```
Running kadet_component_kubernetes.fish with id = cod and config = {'family': 'Gadidae', 'habitat': 'water', 'fins': True}
Running kadet_component_kubernetes.fish with id = blue_shark and config = {'name': 'blue-shark', 'family': 'Carcharhinidae', 'habitat': 'water', 'fins': True}
```

## FAQ

### Contex available to generators

When Kapitan calls your generato classes, these are the fields that will be made available:

| variable              | description                                                    |
|-----------------------|----------------------------------------------------------------|
| self.id               | the id of the generator configuration                          |
| self.name             | if available, the name defined in the config, otherwise the id |
| self.config           | the content of the generator config, with patches applied      |
| self.inventory        | the inventory for the given target                             |
| self.global_inventory | the global inventory available to Kapitan                      |
| self.defaults         | the defaults configuration for this generator                  |
| self.target           | the name of the current target                                 |
| self.patches_applied  | the list of patches that were merged into the original config  |
| self.original_config  | the original unmodified configuration                          |


### `BaseContent` and `BaseStore`

You can attach a generator to derivates of 2 classes which are provided by the `kgenlib` generator, `BaseContent` and `BaseStore`

> Why? Until now, it was difficult for `Kadet`` (and for developers) whether the returning object was meant to be rendered as it is, or was a collection of more objects. We have then decide to provide two new classes with the intention to make this more explicit, and also add more functionalities.


### Multiple generators

Multiple generator classes can register for the same path. This way you could have for instance a "AWS" and a "GCP" terraform generator that use the same configuration, and activate them depending on what you need.
