# Concepts

## **Understanding Kapitan Generators**

### What are Kapitan Generators?
Kapitan generators empower you to utilize the Kapitan inventory's configuration to formulate resources and objects. Instead of relying on jsonnet or kadet directly, envision generators as bespoke templates. They act akin to a personalized Domain Specific Language (DSL) for the exact resource or file you're designing.

### Who is this Guide Aimed At?
Should you aspire to either augment existing generators or architect your own, this guide caters to you. Be aware, familiarity with Kapitan is a prerequisite; thus, basic Kapitan tenets won't be discussed.

### Introducing **klibgen**
`klibgen` is an innovative library crafted to streamline creating new generators. Opting for `klibgen` endows you with several inherent features to elevate your experience:

- **Decorator Utility**: Swiftly morph your class into a generator.
- **Automatic Context Provision**: An innate context is endowed to your class.
- **Defaults Integration**: Incorporate default configurations effortlessly.
- **Post-Creation Modifications**: Amend objects subsequent to their creation.
- **Diverse Generator Support**: Be it target-centric or universal generators, `klibgen` has your back.

### Contextual Elements in Kapitan Generators
Upon Kapitan activating your generator classes, an array of fields are accessible:

| Variable                | Description                                               |
|-------------------------|-----------------------------------------------------------|
| `self.id`               | Unique ID tied to the generator configuration.            |
| `self.name`             | Name stipulated in the config or the designated ID.       |
| `self.config`           | Config content of the generator with patches incorporated.|
| `self.inventory`        | Specific inventory for the stipulated target.             |
| `self.global_inventory` | Kapitan-wide accessible inventory.                        |
| `self.defaults`         | Preset configurations for this specific generator.        |
| `self.target`           | Designation of the ongoing target.                        |
| `self.patches_applied`  | Array of patches amalgamated into the foundational config.|
| `self.original_config`  | The pristine, unaltered configuration.                    |
