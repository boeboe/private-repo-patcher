# Kubernetes private image repository patcher

This contain image mitigates some shortcomings in certain kubernetes operators, namely the lack of being able to pull from private image repositories.

As operators often create their own resources, outside of the control of infrastructure as code repositories, it is often a manual and tedious job to patch [ServiceAccount](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#add-image-pull-secret-to-service-account) objects in order to allow for private image repository pulling.

This container, which can be used as a deployment or a job, automates this task by:
 - creating a [Secret](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/) with proper `.dockerconfigjson` content
 - iterating over [ServiceAccount](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#add-image-pull-secret-to-service-account) object and create or add a proper `imagePullSecrets` stanza
 - iterate over crashloop pods with failure reasons `ImagePullBackOff` or `ErrImagePull` and schedule them for recreation by deleting them

These steps are executed in a loop and can apply to a list of namespaces you define. 

An example [configuration](config/config.yaml) for this patcher looks like this:

```yaml
namespaces:
  - default
  - test
registry:
  email: bartvanbos@gmail.com
  host: harbor.example.com/boeboe
  password: Boeboe@harbor123!
  pullSecretName: private-registry-secret
  username: admin
time:
  interval: 10
  runtime: 60
```

The total `runtime` can be configured in seconds. Setting the runtime to `0` will cause an infite while true loop. The interval configures the waiting time between iterations of the loop described. Once the runtime time has exceeded, the process will exit with code 0.

## Build

In case you want to modify the logic and/or build this container from scratch, the following helper `makefile` targets can help you.

```bash
$ make

  help                           This help
  build                          Build the container
  run                            Run container
  shell                          Run shell in container
  stop                           Stop and remove a running container
  publish                        Tag and publish container
  release                        Make a full release
  deploy-pod                     Deploy in kubernetes as a pod
  undeploy-pod                   Undeploy kubernetes pod
  deploy-job                     Deploy in kubernetes as a job
  undeploy-job                   Undeploy kubernetes job
```

In case you run the container outside kubernetes, you need to bindmount a valid `.kube` directory in order to be able to access a kubernetes API server. Check the `Makefile` for some valid `docker run` examples. Within kubernetes itself, this is handled automatically.

## Deploy

In order to deploy this container, you have the option to chose between a kubernetes job or a deployment, as exampled in the [kubernetes](./kubernetes) folder.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: private-repo-patcher
  namespace: private-repo-patcher
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    k8s-app: private-repo-patcher
  name: private-repo-patcher
rules:
  - apiGroups:
      - ''
    resources:
      - pods
    verbs:
      - delete
      - get
      - list
  - apiGroups:
      - ''
    resources:
      - namespaces
    verbs:
      - get
      - list
  - apiGroups:
      - ''
    resources:
      - secrets
    verbs:
      - create
      - get
      - list
  - apiGroups:
      - ''
    resources:
      - serviceaccounts
    verbs:
      - get
      - list
      - patch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: private-repo-patcher
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: private-repo-patcher
subjects:
  - kind: ServiceAccount
    name: private-repo-patcher
    namespace: private-repo-patcher
---
apiVersion: v1
data:
  config.yaml: |
    namespaces:
      - default
      - test
    registry:
      email: bartvanbos@gmail.com
      host: harbor.example.com/boeboe
      password: Boeboe@harbor123!
      pullSecretName: private-registry-secret
      username: admin
    time:
      interval: 10
      runtime: 600
kind: ConfigMap
metadata:
  name: private-repo-patcher
  namespace: private-repo-patcher
---
apiVersion: batch/v1
kind: Job
metadata:
  name: private-repo-patcher
  namespace: private-repo-patcher
spec:
  template:
    spec:
      containers:
        - env:
            - name: CONF_FILE
              value: /etc/patcher/config.yaml
          image: boeboe/private-repo-patcher:0.1.0
          imagePullPolicy: Always
          name: private-repo-patcher
          resources:
            limits:
              cpu: 250m
              memory: 128Mi
          volumeMounts:
            - mountPath: /etc/patcher
              name: patcher-config
      restartPolicy: OnFailure
      serviceAccountName: private-repo-patcher
      volumes:
        - configMap:
            name: private-repo-patcher
          name: patcher-config
```

A job with a limited runtime is likely the best option in case you have a determinstic number of pods that need images to be pulled from a private repo. You can also choose a deployment with infinite runtime (runtime set to `0`) in case you need persistent patching over a longer period of time.

