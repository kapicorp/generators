# Tutorial

Developing new generators is very easy, thanks to our library [kgenlib](/lib/kgenlib)

In this tutorial we will learn how to create a small generator class for to generate a new Kubernetes CRD object, the `Fish CRD`

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



## Register your generator classes

The library provides a simple Python annotation that registers your generator with Kapitan.

For instance, the following annotation..

```py
@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
)
class GenSimpleFishGenerator(kgenlib.BaseContent):
```

..will tell Kapitan to use your Generator class for inventory paths that match the following structure:

```yaml
parameters:
  kapicorp:
    simple_fish_generator:
      
      cod:   # the generator config id
        # The generator config
        name: demersal fish genus Gadus
        family: Gadidae
      
      # Another generator config block
      blue_shark:
        name: blue shark
        family: Carcharhinidae
```

When Kapitan runs, it will find all the items in dictionary matching the path, and will call your `GenGitHubRepository` passing these configurations alongsite some other context variables.

## Contex available to generators

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

## Multiple generators

Multiple generator classes can register for the same path. This way you could have for instance a "AWS" and a "GCP" terraform generator that use the same configuration, and activate them depending on what you need.


## Initialising the generator

The actual generator makes use of kadet, so you need to be familiar with Kadet concepts

```py
from kapitan.inputs.kadet import inventory, load_from_search_paths

# Attention, make sure you only load this once, to prevent multicurrency issues
kgenlib = load_from_search_paths("kgenlib")

@kgenlib.register_generator(
    path="kapicorp.simple_fish_generator",
)
class GenSimpleFishGenerator(kgenlib.BaseContent):
  def body():
    self.root.name = self.name
    self.root.family = self.config.get("family", "UNKNOWN")


def main(input_params):
    inv = inventory(lazy=True)
    generator = kgenlib.BaseGenerator(inventory=inv)
    store = generator.generate()
    store.process_mutations(input_params.get("mutations", {}))

    return store.dump()
```

## `BaseContent` and `BaseStore`

You can attach a generator to derivates of 2 classes which are provided by the `kgenlib` generator, `BaseContent` and `BaseStore`

> Why? Until now, it was difficult for `Kadet`` (and for developers) whether the returning object was meant to be rendered as it is, or was a collection of more objects. We have then decide to provide two new classes with the intention to make this more explicit, and also add more functionalities.