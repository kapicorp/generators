import logging

logger = logging.getLogger(__name__)

from .common import TerraformResource, TerraformStore, kgenlib


@kgenlib.register_generator(
    path="terraform.gen_github_repository",
    apply_patches=["generators.terraform.defaults.gen_github_repository"],
)
class GenGitHubRepository(TerraformStore):
    def body(self):
        resource_id = self.id
        config = self.config

        branch_protection_config = config.pop("branch_protection", {})
        tag_protection_config = config.pop("tag_protection", {})
        deploy_keys_config = config.pop("deploy_keys", {})
        ruleset_config = config.pop("repository_ruleset", {})
        actions_config = config.pop("actions", {})
        access_permissions_config = config.pop("permissions", {})
        autolink_references_config = config.pop("autolink", {})

        resource_name = self.name
        logger.debug(f"Processing github_repository {resource_name}")
        repository = TerraformResource(
            id=resource_id,
            type="github_repository",
            config=config,
            defaults=self.defaults,
        )
        repository.set()
        repository.filename = "github_repository.tf"

        self.add(repository)

        for branches_name, branches_config in branch_protection_config.items():
            logger.debug(f"Processing branch protection for {branches_name}")
            branch_protection = TerraformResource(
                id=f"{resource_id}_{branches_name}",
                type="github_branch_protection",
                config=branches_config,
                defaults=self.defaults,
            )
            branch_protection.filename = "github_branch_protection.tf"
            branch_protection.set(branch_protection.config)
            branch_protection.add("repository_id", repository.get_reference("node_id"))
            branch_protection.set(
                {"pattern": branches_name}
            )  # Ensures the pattern is unique to the branch name and doesn't default to `main`
            self.add(branch_protection)

        for rule_name, tag_pattern in tag_protection_config.items():
            logger.debug(f"Processing tag protection for {rule_name}")
            tag_protection = TerraformResource(
                id=f"{resource_id}_{rule_name}",
                type="github_repository_tag_protection",
                config={"pattern": tag_pattern},
                defaults=self.defaults,
            )
            tag_protection.filename = "github_repository_tag_protection.tf"
            tag_protection.set(tag_protection.config)
            tag_protection.add("repository", repository.get_reference("name"))
            self.add(tag_protection)

        for deploy_key_name, deploy_key_branches in deploy_keys_config.items():
            logger.debug(f"Processing deploy keys for {deploy_key_name}")
            deploy_key = TerraformResource(
                id=f"{resource_id}_{deploy_key_name}",
                type="github_repository_deploy_key",
                config=deploy_key_branches,
                defaults=self.defaults,
            )
            deploy_key.filename = "github_deploy_key.tf"
            deploy_key.set(deploy_key.config)
            deploy_key.add("repository", repository.get_reference("name"))
            self.add(deploy_key)

        for ruleset_name, ruleset_config in ruleset_config.items():
            logger.debug(f"Processing rulesets for {branches_name}")
            repository_ruleset = TerraformResource(
                id=f"{resource_id}_{ruleset_name}",
                type="github_repository_ruleset",
                config=ruleset_config,
                defaults=self.defaults,
            )
            repository_ruleset.add("name", ruleset_name)
            repository_ruleset.add("repository", repository.get_reference("name"))
            repository_ruleset.filename = "github_repository_ruleset.tf"
            repository_ruleset.set(repository_ruleset.config)
            self.add(repository_ruleset)

        if actions_config.get("access_level") is not None:
            gha_actions_access = TerraformResource(
                id=f"{resource_id}_actions_access",
                type="github_actions_repository_access_level",
                config={
                    "repository": repository.get_reference("name"),
                    "access_level": actions_config.get("access_level"),
                },
            )
            gha_actions_access.filename = "github_repository_actions.tf"
            gha_actions_access.set(gha_actions_access.config)
            gha_actions_access.add("repository", repository.get_reference("name"))
            self.add(gha_actions_access)

        for permission_type, permission_config in access_permissions_config.items():
            logger.debug(f"Processing permissions for {resource_name}")
            for entity, permission in permission_config.items():
                if permission_type == "team":
                    config = {"team_id": f"{entity}", "permission": f"{permission}"}
                else:
                    config = {"username": f"{entity}", "permission": f"{permission}"}
                repository_collaborators = TerraformResource(
                    id=f"{resource_name}_access_permissions".replace(".", ""),
                    type="github_repository_collaborators",
                    config=config,
                )
                repository_collaborators.filename = "github_repository_collaborators.tf"
                repository_collaborators.add(
                    "repository", repository.get_reference("name")
                )
                repository_collaborators.add(
                    permission_type, [repository_collaborators.config]
                )
                self.add(repository_collaborators)

        for key_prefix, target_url in autolink_references_config.items():
            logger.debug(f"Processing autolink referneces for {resource_name}")
            config = {
                "key_prefix": f"{key_prefix}-",
                "target_url_template": f"{target_url}",
            }
            autolink_references = TerraformResource(
                id=f"{key_prefix}".replace(".", ""),
                type="github_repository_autolink_reference",
                config=config,
            )
            autolink_references.filename = "github_repository_autolink_reference.tf"
            autolink_references.set(autolink_references.config)
            autolink_references.add("repository", repository.get_reference("name"))
            self.add(autolink_references)
