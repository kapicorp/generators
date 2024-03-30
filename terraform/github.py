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

        resource_name = self.name
        logger.debug(f"Processing github_repository {resource_name}")
        repository = TerraformResource(
            id=resource_id,
            type="github_repository",
            config=config,
            defaults=self.defaults,
        )
        repository.set(config)
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
