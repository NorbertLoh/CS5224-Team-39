# Shared modules

Reusable modules called from both `envs/dev` and `envs/demo`, such as network, ingress, ECS service and data stores. Add each module with the task that first needs it (W02 onwards), and keep environment-specific values in the environment roots.
