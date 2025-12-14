#!/bin/bash

# Kubernetes Cluster Aliases
# Usages:
#   kcmd get nodes
#   kgpu get pods
#   kcpu get pods

alias kcmd='kubectl --kubeconfig ~/.kube/config-command-cluster'
alias kgpu='kubectl --kubeconfig ~/.kube/config-gpu-cluster'
alias kcpu='kubectl --kubeconfig ~/.kube/config-cpu-cluster'

# Karmada Alias (Optional but useful)
alias kk='kubectl --kubeconfig /etc/karmada/karmada-apiserver.config'

# Completion (Optional - uncommment if you want completion for these aliases)
# source <(kubectl completion bash)
# complete -o default -F __start_kubectl kcmd
# complete -o default -F __start_kubectl kgpu
# complete -o default -F __start_kubectl kcpu
