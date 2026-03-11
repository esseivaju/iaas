## Ingresses
There are two ingresses for the deployment, one for for GRPC traffic directed to envoy/triton in [triton-cluster.yaml](triton-cluster.yaml), and another ingress in [ingress.yaml](ingress.yaml) for regular http traffic to grafana / the triton controller.

## Helm Chart
ssl certificates are generated using [tls-acme](https://github.com/NERSC/spin-helm/tree/main/tls-acme) helm chart. Example values for that chart are found in [values-ingress.yaml](values-ingress.yaml) and [values-triton-cluster.yaml](values-triton-cluster.yaml)