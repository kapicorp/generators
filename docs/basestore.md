# BaseStore

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