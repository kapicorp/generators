import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

from kapitan.inputs.kadet import Dict

from .common import (
    TerraformData,
    TerraformResource,
    TerraformStore,
    cleanup_terraform_resource_id,
    kgenlib,
)
from .servicedirectory import gen_service_directory_service


class GoogleResource(TerraformResource):
    def body(self):
        self.resource.project = self.config.get("project")
        super().body()


@kgenlib.register_generator(path="gen_google_organization_iam_policy")
class GenGoogleOrgPolicyPolicy(TerraformStore):
    def body(self):
        self.filename = "gen_google_organization_iam_policy.tf"
        bindings = self.config
        id = self.id
        gcp_organization_id = self.inventory.parameters.get("gcp_organization_id")

        roles_dict = defaultdict(list)
        roles_dict.update()

        for name, spec in bindings.items():
            roles = spec.get("roles")
            role_id = spec.get("id", name)
            for role in roles:
                roles_dict[role].append(role_id)

        policy_data = {
            "bindings": [
                {"role": role, "members": members}
                for role, members in roles_dict.items()
            ]
        }

        policy_file = kgenlib.BaseContent.from_dict(policy_data)
        policy_file.filename = "policy"
        self.add(policy_file)

        legacy_policy = self.inventory.parameters.get("legacy_policy", {})
        legacy_policy_file = kgenlib.BaseContent.from_dict(legacy_policy)
        legacy_policy_file.filename = "policy-legacy"
        self.add(legacy_policy_file)

        iam_org_policy = GoogleResource(
            id=id,
            type="google_organization_iam_policy",
        )

        iam_org_policy.resource.pop(
            "project"
        )  # project is not supported for google_organization_iam_policy
        iam_org_policy.resource.org_id = bindings.get(
            "gcp_organization_id", gcp_organization_id
        )
        iam_org_policy.resource.policy_data = json.dumps(policy_data)

        self.add(iam_org_policy)


@kgenlib.register_generator(path="terraform.gen_google_org_policy_policy_org")
class GenGoogleOrgPolicyPolicy(TerraformStore):
    def body(self):
        self.filename = "gen_google_org_policy_policy.tf"
        config = self.config
        id = self.id

        policy = GoogleResource(
            id=self.id.replace(".", "_"),
            type="google_org_policy_policy",
            config=config,
            defaults=self.defaults,
        )

        organization_id = self.inventory.parameters.get("gcp_organization_id")
        parent = config.get("parent", f"organizations/{organization_id}")
        policy.resource.pop(
            "project"
        )  # project is not supported for google_org_policy_policy
        policy.resource.name = f"{parent}/policies/{id}"
        policy.resource.parent = parent

        if config.get("reset", False):
            policy.resource.spec.reset = config.get("reset", False)
        else:
            if config.get("enforce", False):
                policy.resource.spec.rules.enforce = config.get("enforce", False)
            elif config.get("default") == "allow":
                policy.resource.spec.rules.allow_all = "TRUE"
            elif config.get("default") == "deny":
                policy.resource.spec.rules.deny_all = "TRUE"
            else:
                config.get("values", {})
                values = config.get("values", {})
                allowed_values = values.get("allowed_values", {})
                denied_values = values.get("denied_values", {})
                policy.resource.spec.rules.setdefault("values", {})[
                    "allowed_values"
                ] = allowed_values
                policy.resource.spec.rules.setdefault("values", {})[
                    "denied_values"
                ] = denied_values

        policy.filename = self.filename
        self.add(policy)


@kgenlib.register_generator(path="isoflow.graphs")
class GenGoogleComputeAddress(TerraformStore):
    address: dict = {"type": "INTERNAL", "subnetwork": "default"}
    dns: dict = {"type": "A", "ttl": "600"}

    def body(self):
        self.filename = "gen_google_compute_address.tf"
        config = self.config
        inputs = config["generate_isoflow_endpoint"]
        if "url" not in inputs:
            raise ValueError(
                "string `url` expected as input to generate_isoflow_endpoint"
            )
        if "dns" not in inputs:
            raise ValueError(
                "object `dns` expected as input to generate_isoflow_endpoint"
            )

        dns_cfg = inputs["dns"]
        url = inputs["url"].strip(".")
        cluster_cfg = config["cluster_cfg"]
        region = config["cluster_cfg"]["location"]

        endpoint_id = f"{config.name}-{config.namespace}-{cluster_cfg.name}"

        internal_cluster_named_ip = self.inventory.parameters.get(
            "internal_cluster_named_ip"
        )
        gateway_address = TerraformData(
            id="gateway",
            type="google_compute_address",
            defaults=self.defaults,
            config=config,
        )
        gateway_address.add("name", internal_cluster_named_ip)
        gateway_address.add("region", region)
        self.add(gateway_address)

        ## TODO(ademaria) remove this block after full gateway migration
        address = GoogleResource(
            id=endpoint_id,
            type="google_compute_address",
            defaults=self.defaults,
            config=config,
        )

        address.resource.name = endpoint_id
        address.resource.address_type = self.address["type"]
        address.resource.subnetwork = self.address["subnetwork"]

        address.resource.region = region

        if self.config.get("load_balancer_ip", None):
            self.add(address)

        ## END

        ip_address_gateway = gateway_address.get_reference(wrap=True, attr="address")

        rule = GoogleResource(
            id=endpoint_id,
            type="google_dns_record_set",
            defaults=self.defaults,
            config=config,
        )

        rule.resource.name = f"{url}."
        rule.resource.managed_zone = dns_cfg.zone_name
        rule.resource.type = self.dns["type"]
        rule.resource.ttl = self.dns["ttl"]
        rule.resource.rrdatas = [ip_address_gateway]

        if self.config.get("enable_anyflow_migration", False):
            rule.resource.name = f"isoflow.{rule.resource.name}"

        self.add_list([rule])

        sd_namespace_id = config.cluster_cfg.name
        sd_project_id = config.cluster_cfg.gcp_project_id
        sd_location = config.cluster_cfg.location

        self.add(
            network := TerraformData(
                id="project", type="google_project", defaults=self.defaults, config={}
            )
        )

        network.add("project_id", sd_project_id)

        self.add_list(
            gen_service_directory_service(
                dict(
                    namespace_id=sd_namespace_id,
                    service_id=self.name,
                    project_id=sd_project_id,
                    location=sd_location,
                    host=config.get("generate_isoflow_endpoint")["url"],
                    endpoints={
                        "http": dict(
                            endpoint_id="http",
                            network="projects/${data.google_project.project.number}/locations/global/networks/default",
                            address=ip_address_gateway,
                            healthcheck_path="/",
                            port=80,
                            metadata=dict(
                                environment=sd_namespace_id,
                                location=sd_location,
                            ),
                        )
                    },
                ),
                self.defaults,
            )
        )


@kgenlib.register_generator(path="ingresses")
class GenIngressResources(TerraformStore):
    def body(self):
        config = self.config
        id = self.id
        self.filename = "ingresses_resources.tf"

        if config.get("dns", False):
            dns_config = config["dns"]
            for rule in config.get("rules", []):
                if rule.get("host", False):
                    dns_record = GoogleResource(
                        id=id,
                        type="google_dns_record_set",
                        defaults=self.defaults,
                        config=config.get("google_dns_record_set", {}),
                    )

                    dns_record.set()

                    dns_name = rule["host"].strip(".")
                    tf_ip_ref = dns_config["tf_ip_ref"]
                    dns_record.resource.rrdatas = [f"${{{tf_ip_ref}.address}}"]

                    dns_record.resource.name = f"{dns_name}."
                    dns_record.filename = self.filename
                    self.add(dns_record)


@kgenlib.register_generator(path="terraform.gen_google_redis_instance")
class GenRedisInstance(TerraformStore):
    def body(self):
        config = self.config
        defaults = config.pop("default_config", {})
        config = {**defaults, **config}
        name = self.name
        resource_id = self.id

        instance = GoogleResource(
            id=resource_id,
            type="google_redis_instance",
            defaults=self.defaults,
            config=config,
        )

        instance.resource.name = name
        instance.resource.tier = config["tier"]
        instance.resource.memory_size_gb = config["memory_size_gb"]
        instance.resource.region = config["region"]
        instance.resource.labels = instance.config.get("labels", {})

        record = GoogleResource(
            id=resource_id,
            type="google_dns_record_set",
            defaults=self.defaults,
            config=config,
        )

        dns_cfg = config["dns"]
        record.resource.name = f'{config["endpoint"]}.'
        record.resource.managed_zone = dns_cfg["zone_name"]
        record.resource.type = dns_cfg["type"]
        record.resource.ttl = dns_cfg.get("ttl", 600)
        record.resource.rrdatas = [f"${{google_redis_instance.{resource_id}.host}}"]

        resources = [instance, record]
        for r in resources:
            r.filename = f"{resource_id}_cluster.tf"

        self.add_list(resources)


@kgenlib.register_generator(path="terraform.gen_google_compute_global_address")
class GenGoogleGlobalComputeAddress(TerraformStore):
    def body(self):
        self.filename = "gen_google_compute_global_address.tf"

        config = self.config
        name = self.name
        id = self.id

        ip_address = GoogleResource(
            id=id,
            type="google_compute_global_address",
            defaults=self.defaults,
            config=config,
        )

        ip_address.set()
        ip_address.filename = self.filename

        self.add(ip_address)


@kgenlib.register_generator(path="terraform.gen_google_compute_address")
class GenGoogleComputeAddress(TerraformStore):
    def body(self):
        self.filename = "gen_google_compute_address.tf"

        config = self.config
        id = self.id

        ip_address = GoogleResource(
            id=id,
            type="google_compute_address",
            defaults=self.defaults,
            config=config,
        )

        ip_address.set()
        ip_address.filename = self.filename

        self.add(ip_address)


@kgenlib.register_generator(path="terraform.gen_google_service_account")
class GenGoogleServiceAccount(TerraformStore):
    def body(self):
        self.filename = "gen_google_service_account.tf"
        resource_id = self.id
        config = self.config
        resource_name = self.name

        sa = GoogleResource(
            id=resource_name,
            type="google_service_account",
            config=config,
            defaults=self.defaults,
        )
        sa_account_id = config.get("account_id", resource_name)
        sa.resource.account_id = sa_account_id
        sa.resource.display_name = config.get("display_name", resource_name)
        sa.resource.description = config.get("description")
        sa.filename = self.filename

        self.add(sa)

        if config.get("bindings", {}):
            for binding_role, binding_config in config.bindings.items():
                binding_id = binding_role.split("/")[1].replace(".", "_")
                sa_binding = GoogleResource(
                    id=f"{resource_id}_{binding_id}",
                    type="google_service_account_iam_binding",
                    config=config,
                    defaults=self.defaults,
                )
                sa_binding.resource.service_account_id = sa.get_reference(
                    attr="name", wrap=True
                )
                sa_binding.resource.role = binding_role
                sa_binding.resource.members = binding_config.members
                sa_binding.filename = self.filename
                sa_binding.resource.depends_on = [sa.get_reference(wrap=False)]
                sa_binding.resource.pop(
                    "project"
                )  # `project` is not supported for `service_account_iam_binding`

                self.add(sa_binding)

        for iam_member_config in config.get("service_account_iam", []):
            member = iam_member_config.member
            sa_name = cleanup_terraform_resource_id(member.split("/")[-1])
            service_account_id = sa.get_reference(attr="name", wrap=True)

            role = iam_member_config.role
            iam_id = role.split("/")[1].replace(".", "_")
            iam_id = f"{iam_id}_{sa_name}"

            iam_member = GoogleResource(
                id=f"{resource_id}_{iam_id}",
                type="google_service_account_iam_member",
                config=config,
                defaults=self.defaults,
            )
            iam_member.filename = self.filename
            iam_member.resource.service_account_id = service_account_id
            iam_member.resource.role = role
            iam_member.resource.member = member
            iam_member.resource.depends_on = [sa.get_reference(wrap=False)]
            iam_member.resource.pop(
                "project"
            )  # `project` is not supported for `service_account_iam_binding`

            self.add(iam_member)

        for iam_member_config in config.get("service_account_iam_for_self", []):
            member = sa.get_reference(attr="member", wrap=True)
            service_account_id = iam_member_config.service_account_id
            sa_name = "self_" + cleanup_terraform_resource_id(
                service_account_id.split("/")[-1]
            )

            role = iam_member_config.role
            iam_id = role.split("/")[1].replace(".", "_")
            iam_id = f"{iam_id}_{sa_name}"

            iam_member = GoogleResource(
                id=f"{resource_id}_{iam_id}",
                type="google_service_account_iam_member",
                config=config,
                defaults=self.defaults,
            )
            iam_member.filename = self.filename
            iam_member.resource.service_account_id = service_account_id
            iam_member.resource.role = role
            iam_member.resource.member = member
            iam_member.resource.depends_on = [sa.get_reference(wrap=False)]
            iam_member.resource.pop(
                "project"
            )  # `project` is not supported for `service_account_iam_binding`

            self.add(iam_member)

        if config.get("roles", {}):
            for role_item in config.roles:
                role_id = role_item.split("/")[1].replace(".", "_")
                role_name = f"{resource_name}_{role_id}"
                sa_role = GoogleResource(
                    id=role_name,
                    type="google_project_iam_member",
                    config=config,
                    defaults=self.defaults,
                )
                sa_role.resource.role = role_item
                sa_role.filename = self.filename
                sa_role.resource.member = (
                    f"serviceAccount:{sa.get_reference(attr='email', wrap=True)}"
                )
                sa_role.resource.depends_on = [sa.get_reference(wrap=False)]
                self.add(sa_role)

        if config.get("bucket_iam"):
            for config_bucket_name, bucket_config in config.bucket_iam.items():
                bucket_name = bucket_config.get("name", config_bucket_name)
                bucket_iam_name = f"{resource_name}_{bucket_name}"

                for role in bucket_config.roles:
                    role_id = role.split("/")[1].replace(".", "_")
                    bucket_role_name = f"{bucket_iam_name}_{role_id}"
                    bucket_role = GoogleResource(
                        id=bucket_role_name,
                        type="google_storage_bucket_iam_member",
                        config=config,
                        defaults=self.defaults,
                    )
                    bucket_role.resource.bucket = bucket_name
                    bucket_role.resource.role = role
                    bucket_role.resource.pop("project")
                    bucket_role.resource.member = (
                        f"serviceAccount:{sa.get_reference(attr='email', wrap=True)}"
                    )
                    bucket_role.filename = self.filename
                    bucket_role.resource.depends_on = [sa.get_reference(wrap=False)]
                    self.add(bucket_role)

        if config.get("pubsub_topic_iam"):
            for topic_name, topic_config in config.pubsub_topic_iam.items():
                if "topic" in topic_config:
                    topic_name = topic_config.topic
                topic_iam_name = f"{resource_name}_{topic_name}"
                project_name = topic_config.project

                for role in topic_config.roles:
                    role_id = role.split("/")[1].replace(".", "_")
                    topic_role_name = f"{topic_iam_name}_{role_id}"
                    topic_role = GoogleResource(
                        id=topic_role_name,
                        type="google_pubsub_topic_iam_member",
                        config=config,
                        defaults=self.defaults,
                    )
                    topic_role.resource.project = project_name
                    topic_role.resource.topic = topic_name
                    topic_role.resource.role = role
                    topic_role.resource.member = (
                        f"serviceAccount:{sa.get_reference(attr='email', wrap=True)}"
                    )
                    topic_role.resource.depends_on = [sa.get_reference(wrap=False)]
                    topic_role.filename = self.filename
                    self.add(topic_role)

        if config.get("pubsub_subscription_iam"):
            for (
                subscription_name,
                subscription_config,
            ) in config.pubsub_subscription_iam.items():
                subscription_iam_name = f"{resource_name}_{subscription_name}"
                project_name = subscription_config.project

                for role in subscription_config.roles:
                    role_id = role.split("/")[1].replace(".", "_")
                    subscription_role_name = f"{subscription_iam_name}_{role_id}"
                    subscription_role = GoogleResource(
                        id=subscription_role_name,
                        type="google_pubsub_subscription_iam_member",
                        config=config,
                        defaults=self.defaults,
                    )
                    subscription_role.resource.project = project_name
                    subscription_role.resource.subscription = (
                        subscription_config.subscription
                    )
                    subscription_role.resource.role = role
                    subscription_role.resource.depends_on = [
                        sa.get_reference(wrap=False)
                    ]
                    subscription_role.resource.member = (
                        f"serviceAccount:{sa.get_reference(attr='email', wrap=True)}"
                    )
                    subscription_role.filename = self.filename
                    self.add(subscription_role)

        if config.get("project_iam"):
            for project_name, iam_config in config.project_iam.items():
                if "project" in iam_config:
                    project_name = iam_config.project
                project_iam_name = f"{resource_name}_{project_name}"

                for role in iam_config.roles:
                    role_id = role.split("/")[1].replace(".", "_")
                    iam_member_resource_name = f"{project_iam_name}_{role_id}"
                    iam_member = GoogleResource(
                        id=iam_member_resource_name,
                        type="google_project_iam_member",
                        config=config,
                        defaults=self.defaults,
                    )
                    iam_member.resource.project = project_name
                    iam_member.resource.role = role
                    iam_member.resource.depends_on = [sa.get_reference(wrap=False)]
                    iam_member.resource.member = (
                        f"serviceAccount:{sa.get_reference(attr='email', wrap=True)}"
                    )
                    iam_member.filename = self.filename
                    self.add(iam_member)

        for repo_id, roles in config.get("artifact_registry_iam", {}).items():
            for role in roles:
                repo_iam_member_cfg = {
                    "repo_id": repo_id,
                    "role": role,
                    "member": f"serviceAccount:{sa.get_reference('email')}",
                    "member_name": sa_account_id,
                }
                repo_iam_member = gen_artifact_registry_repository_iam_member(
                    repo_iam_member_cfg, self.defaults
                )
                repo_iam_member.resource.depends_on = [sa.get_reference(wrap=False)]
                self.add(repo_iam_member)


@kgenlib.register_generator(
    path="terraform.gen_google_container_cluster",
    apply_patches=["generators.terraform.defaults.gen_google_container_cluster"],
)
class GenGoogleContainerCluster(TerraformStore):
    def body(self):
        self.filename = "gen_google_container_cluster.tf"
        id = self.id
        config = self.config
        name = self.name

        pools = config.pop("pools", {})

        cluster = GoogleResource(
            id=id,
            type="google_container_cluster",
            defaults=self.defaults,
            config=config,
        )
        cluster.resource.name = name
        cluster.set()
        cluster.filename = self.filename
        cluster.resource.setdefault("depends_on", []).append(
            "google_project_service.container"
        )

        self.add(cluster)

        for pool_name, pool_config in pools.items():
            # pools are enabled by default
            disabled = pool_config.pop("disabled", False)
            if disabled:
                continue

            pool = GoogleResource(
                id=pool_name,
                type="google_container_node_pool",
                config=pool_config,
                defaults=self.defaults,
            )
            pool.set()
            pool.resource.update(pool_config)
            pool.resource.cluster = cluster.get_reference(attr="id", wrap=True)
            pool.filename = self.filename

            if not pool_config.get("autoscaling", {}):
                # If autoscaling config is not defined or empty, make sure to remove it from the pool config
                pool.resource.pop("autoscaling", {})
            else:
                # If autoscaling is configured, remove static node count
                # and set initial node count to the lowest allowed in autoscaling
                pool.resource.pop("node_count", None)
                if "initial_node_count" not in pool.resource:
                    pool.resource["initial_node_count"] = pool_config["autoscaling"][
                        "total_min_node_count"
                    ]

            self.add(pool)

        # Creates a configuration file for the cluster in the remote mcp repository
        logger.debug(f"Processing configuration for cluster {name}")
        configuration = TerraformResource(
            id=name,
            type="github_repository_file",
            config=config,
            defaults=self.defaults,
        )

        configuration.resource.branch = "main"
        configuration.resource.file = (
            f"{cluster.get_reference(attr='project', wrap=True)}/{name}.yml"
        )
        configuration.resource.repository = "mcp-remote"
        configuration.resource.content = f'${{templatefile("cluster_inventory.tftpl", {{ cluster = {cluster.get_reference(wrap=False)} }})}}'
        configuration.resource.commit_message = "Managed by Kapitan"
        configuration.resource.commit_author = "Kapitan User"
        configuration.resource.overwrite_on_create = True

        self.add(configuration)


@kgenlib.register_generator(
    path="terraform.gen_google_storage_bucket",
    apply_patches=["generators.terraform.defaults.gen_google_storage_bucket"],
)
class GoogleStorageBucketGenerator(TerraformStore):
    location: str = "EU"

    def body(self):
        self.filename = "gen_google_storage_bucket.tf"
        resource_id = self.id
        config = self.config
        resource_name = self.name
        bucket = GoogleResource(
            type="google_storage_bucket",
            id=resource_id,
            config=config,
            defaults=self.defaults,
        )
        bucket_config = bucket.config
        bucket.add("name", resource_name)
        bucket.filename = self.filename
        bucket.add("location", bucket_config.get("location", self.location))
        bucket.add("versioning", bucket_config.get("versioning", {}))
        bucket.add("lifecycle_rule", bucket_config.get("lifecycle_rule", []))
        bucket.add("cors", bucket_config.get("cors", []))
        bucket.add("labels", bucket_config.get("labels", {}))
        bucket.add(
            "uniform_bucket_level_access",
            bucket_config.get("uniform_bucket_level_access", True),
        )

        self.add(bucket)

        if config.get("bindings", {}):
            for binding_role, binding_config in config.bindings.items():
                for member in binding_config.members:
                    binding_id = binding_role.split("/")[1].replace(".", "_")
                    binding_id = f"{resource_id}_{binding_id}_{member}"
                    binding_id = (
                        binding_id.replace("@", "_")
                        .replace(".", "_")
                        .replace(":", "_")
                        .lower()
                    )
                    bucket_binding = GoogleResource(
                        type="google_storage_bucket_iam_member",
                        id=binding_id,
                        config=config,
                        defaults=self.defaults,
                    )
                    bucket_binding.filename = self.filename
                    bucket_binding.add(
                        "bucket", bucket.get_reference(attr="name", wrap=True)
                    )
                    bucket_binding.add("role", binding_role)
                    bucket_binding.add("member", member)
                    bucket_binding.resource.pop(
                        "project"
                    )  # `project` is not supported for `google_storage_bucket_iam_binding`

                    self.add(bucket_binding)


@kgenlib.register_generator(path="terraform.gen_google_artifact_registry_repository")
class GoogleArtifactRegistryGenerator(TerraformStore):
    def body(self):
        self.filename = "gen_google_artifact_registry_repository.tf"
        resource_id = cleanup_terraform_resource_id(self.id)
        config = self.config
        iam_members = config.pop("iam_members", [])

        config.setdefault("repository_id", self.name)
        repo = GoogleResource(
            type="google_artifact_registry_repository",
            id=resource_id,
            config=config,
            defaults=self.defaults,
        )
        repo.set()

        config = Dict(repo.config)

        for member_cfg in iam_members:
            for role in member_cfg.get("roles", []):
                repo_iam_member_cfg = {
                    "repo_id": f"{config.project}/{config.location}/{config.repository_id}",
                    "role": role,
                    "member": member_cfg["member"],
                }
                repo_iam_member = gen_artifact_registry_repository_iam_member(
                    repo_iam_member_cfg, self.defaults
                )
                repo_iam_member.resource.depends_on = [repo.get_reference(wrap=False)]
                self.add(repo_iam_member)

        self.add(repo)


def gen_artifact_registry_repository_iam_member(config, defaults):
    role = config.get("role")

    gcp_project, location, repo_name = config.get("repo_id").split("/")
    repo_id = f"projects/{gcp_project}/locations/{location}/repositories/{repo_name}"
    member = config.get("member")

    member_name = config.get("member_name")
    if member_name is None:
        # turn serviceAccount:service-695333208979@gcp-sa-aiplatform.iam.gserviceaccount.com
        # into service-695333208979
        member_name = config.get("member").split("@")[0]
        member_name = member_name.split(":")[1]

    role_id = role.split("/")[-1].replace(".", "-")
    name = config.get("name", f"{member_name}-{repo_name}-{role_id}").replace(".", "-")
    if name[0].isdigit():
        name = f"_{name}"
    iam_policy_config = {
        "project": gcp_project,
        "location": location,
        "repository": repo_id,
        "role": role,
        "member": member,
    }
    repo_iam_member = GoogleResource(
        type="google_artifact_registry_repository_iam_member",
        id=name,
        config=iam_policy_config,
        defaults=defaults,
    )
    repo_iam_member.set(iam_policy_config)

    return repo_iam_member
