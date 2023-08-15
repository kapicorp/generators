# Developing generators

Developing new generators is very easy, thanks to our library [kgenlib](/lib/kgenlib)

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


---

## `BaseContent` Class

The `BaseContent` class extends the `BaseModel` class and provides methods to manipulate and work with content in various formats.

`BaseContent` represents an object to be *rendered*: think of it as a (single item) JSON or YAML content. For instance, this could be the content of a `BaseContent` object:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: shark
  namespace: ocean
spec:
  ports:
    - name: shark
      port: 8080
      protocol: TCP
      targetPort: 8080
  selector:
    app: shark
  sessionAffinity: None
  type: ClusterIP
```

---

### Attributes

#### `content_type`

- **Type**: ContentType (default is `ContentType.YAML`)
- **Description**: Defines the type of content (e.g., YAML).

#### `filename`

- **Type**: str (default is "output")
- **Description**: The name of the output file.

### Methods

#### `body(self)`

This is an abstract method intended to be overridden by derived classes. Defines the body content.

#### `from_baseobj(cls, baseobj: BaseObj) -> BaseContent`

**Class Method**  
Initializes a `BaseContent` using a `BaseObj`.

- **Parameters**:
  - `baseobj`: An instance of `BaseObj`.
- **Returns**: A new `BaseContent` instance.

#### `from_yaml(cls, file_path: str) -> List[BaseContent]`

**Class Method**  
Creates a list of `BaseContent` instances from a YAML file.

- **Parameters**:
  - `file_path`: Path to the YAML file.
- **Returns**: List of `BaseContent` instances.

#### `from_dict(cls, dict_value: dict) -> BaseContent`

**Class Method**  
Creates a `BaseContent` instance from a dictionary.

- **Parameters**:
  - `dict_value`: Dictionary to initialize from.
- **Returns**: A new `BaseContent` instance.

#### `parse(self, content: Dict)`

Parses content into the `BaseContent` instance.

- **Parameters**:
  - `content`: Dictionary to parse.

#### `findpath(obj, path: str)`

**Static Method**  
Finds a nested attribute using dot notation.

- **Parameters**:
  - `obj`: Object to search within.
  - `path`: Dot notation path of the attribute.
- **Returns**: Value found at the specified path.

#### `mutate(self, mutations: List)`

Mutates the content based on provided mutations.

- **Parameters**:
  - `mutations`: List of mutation rules.

#### `match(self, match_conditions: dict) -> bool`

Matches the content against provided conditions.

- **Parameters**:
  - `match_conditions`: Dictionary of match conditions.
- **Returns**: Boolean indicating match success.

#### `patch(self, patch: dict)`

Applies a patch to the content.

- **Parameters**:
  - `patch`: Dictionary representing the patch to be applied.

---


## `BaseStore` class

The `BaseStore` class extends the `BaseModel` class and provides methods to manipulate a collection of `BaseContent` objects

This is the class that will eventually be returned back to Kapitan from Kadet.



### Attributes

#### `content_list`

- **Type**: List of `BaseContent`
- **Description**: Contains the list of `BaseContent` objects stored.

### Methods

#### `from_yaml_file(cls, file_path: str) -> BaseStore`

**Class Method**  
Loads a `BaseStore` instance from a YAML file.

- **Parameters**:
  - `file_path`: Path to the YAML file.
- **Returns**: A new `BaseStore` instance populated with `BaseContent` objects from the YAML file.

#### `add(self, object: Any)`

Adds an object or list of objects to the store.

- **Parameters**:
  - `object`: Object to add. Can be of type `BaseContent`, `BaseStore`, `BaseObj`, or list.

#### `add_list(self, contents: List[BaseContent])`

Adds a list of `BaseContent` objects to the store.

- **Parameters**:
  - `contents`: List of `BaseContent` objects.

#### `import_from_helm_chart(self, **kwargs)`

Imports `BaseContent` objects from a Helm chart.

- **Parameters**:
  - `**kwargs`: Keyword arguments for the `HelmChart` object.

#### `apply_patch(self, patch: Dict)`

Applies a patch to every `BaseContent` in the store.

- **Parameters**:
  - `patch`: Dictionary representing the patch to apply.

#### `process_mutations(self, mutations: Dict)`

Processes mutations on each `BaseContent` in the store.

- **Parameters**:
  - `mutations`: Dictionary of mutations to process.

#### `get_content_list(self) -> List[BaseContent]`

Returns the list of `BaseContent` objects stored in the `BaseStore`.

- **Returns**: List of `BaseContent` objects.

#### `dump(self, output_filename: Optional[str] = None, already_processed: Optional[bool] = False) -> Any`

Dumps the `BaseStore` contents. 

- **Parameters**:
  - `output_filename`: Optional output filename.
  - `already_processed`: Indicates if the content was processed before.
- **Returns**: A list or dictionary of dumped contents.


Certainly! Here's the documentation markup for the `BaseGenerator` class:

---

## `BaseGenerator` Class

Represents a base generator for handling generators functions.

### Initialization

`BaseGenerator(inventory: Dict, store: BaseStore = None, defaults_path: str = None)`

- **Parameters**:
  - `inventory` (Dict): The main content inventory.
  - `store` (BaseStore, optional): The storage for generated content. Defaults to a new `BaseStore` instance.
  - `defaults_path` (str, optional): Path to the default settings for the generator.

### Attributes

#### `inventory`

- **Type**: Dict
- **Description**: The main content inventory.

#### `global_inventory`

- **Type**: Function result
- **Description**: The global content inventory retrieved from `inventory_global()`.

#### `generator_defaults`

- **Type**: Variable Type (based on the result of `findpath`)
- **Description**: Defaults used by the generator, retrieved from the main inventory.

#### `store`

- **Type**: BaseStore
- **Description**: The storage for generated content.

### Methods

#### `expand_and_run(self, func, params, inventory=None)`

Expands provided configurations and runs the specified function on them.

- **Parameters**:
  - `func`: The function to run on each configuration.
  - `params`: Parameters to guide the expansion.
  - `inventory` (optional): The inventory to use. Defaults to the object's main inventory.

#### `generate(self) -> BaseStore`

Executes registered generators based on their activation paths and global flags.

- **Returns**: The updated `BaseStore` containing the generated content.

### Exceptions Raised

#### `CompileError`

Raised when neither 'path' nor 'activation_property' is provided in `expand_and_run`.