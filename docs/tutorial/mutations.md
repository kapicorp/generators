# Mutations

## **Mutations in `kgenlib`**

### **Introduction to Mutations**

In `kgenlib`, "Mutations" are tools that let you modify the objects generated based on certain criteria. They provide more granular control over the generation process, allowing you to dynamically adjust outputs based on predefined rules.

### **Example: Mutating Helm Chart Manifests**

Given a configuration producing manifests from a helm chart:

```yaml
charts:
  keel:
    chart_dir: ${keel:chart_dir}
    helm_params:
      namespace: ${keel:namespace}
      name: ${keel:chart_name}
      output_file: ${keel:chart_name}.yml
    helm_values: ${keel:helm_values}
```

You can set up the following mutations to adjust the objects the Helm chart generates:

```yaml
mutations:
  bundle:
    - conditions:
        kind: [CustomResourceDefinition]
      filename: keel-crds
    - conditions:
        kind: ['*']
      filename: keel-bundle
  delete:
    - conditions:
        kind: [ConfigMap]
        metadata.name: ["keel-config"]
  patch:
    - conditions:
        kind: [CustomResourceDefinition]
      patch:
        metadata:
          annotations:
            argocd.argoproj.io/sync-options: SkipDryRunOnMissingResource=true,Replace=true
```

### **Mutation Types**

- **Bundle**: Dictates where objects are stored.
  - `filename`: Redefines the file where objects matching conditions are placed.
  
- **Patch**: Add or remove patches to objects that match given conditions.
  
- **Delete**: Removes objects that fit the criteria.

### **Advanced `Bundle` Use**

The `filename` parameter in the `bundle` mutation is an "f-format" string, accepting the resource content. 

This means configurations like:

```yaml
mutations:
  bundle:
    - conditions:
        kind: ['*']
      filename: "{content.metadata.namespace}/{content.metadata.name}
```

Can dynamically relocate generated files into subdirectories based on their namespace, adding another layer of organization.