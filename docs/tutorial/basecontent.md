# BaseContent

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