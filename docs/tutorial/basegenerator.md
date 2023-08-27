# BaseGenerator

Represents a base generator for handling generators functions.

## Initialization

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