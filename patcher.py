#!/usr/bin/env python3

import argparse
import base64
import json
import sys
import yaml

from kubernetes import client, config
from time import sleep, time


def parse_config(*, file):
  with open(file, "r") as stream:
    try:
      return yaml.safe_load(stream)
    except yaml.YAMLError as exc:
      print(exc)


def patch(*, myconfig):
  secretname = myconfig["registry"]["pullSecretName"]
  for ns in myconfig["namespaces"]:
    if namespace_exists(namespace=ns):
      if not secret_exists(secretname=secretname, namespace=ns):
        create_secret(myconfig=myconfig, namespace=ns)
        print(f"Created secret '{secretname}' in namespace '{ns}'")
      for sa in K8S.list_namespaced_service_account(ns).items:
        if not sa.image_pull_secrets or not serviceaccount_has_secret(secretname=secretname, serviceaccount=sa):
          patch_serviceaccount(secretname=secretname, namespace=ns, serviceaccount=sa.metadata.name)
          print(f"Patched service account '{sa.metadata.name}' in namespace '{ns}' with secret '{secretname}'")


def create_secret(*, myconfig, namespace):
  cred_payload = {
    "auths": {
      myconfig["registry"]["host"]: {
        "username": myconfig["registry"]["username"],
        "password": myconfig["registry"]["password"],
        "email": myconfig["registry"]["email"],
      }
    }
  }
  data = {
    ".dockerconfigjson": base64.b64encode(
      json.dumps(cred_payload).encode()
    ).decode()
  }
  secret = client.V1Secret(
    api_version="v1",
    data=data,
    kind="Secret",
    metadata=dict(name=myconfig["registry"]["pullSecretName"], namespace=namespace),
    type="kubernetes.io/dockerconfigjson",
  )
  K8S.create_namespaced_secret(namespace, secret)


def patch_serviceaccount(*, secretname, namespace, serviceaccount):
    body = K8S.read_namespaced_service_account(serviceaccount, namespace)
    if body.image_pull_secrets:
      body.image_pull_secrets.append(
        {
          "name": secretname
        }
      )
    else:
      body.image_pull_secrets = [
        {
          "name": secretname
        }
      ]
    K8S.patch_namespaced_service_account(
      name=serviceaccount,
      namespace=namespace,
      body=body,
      pretty="true",
    )


def namespace_exists(*, namespace):
  try:
    K8S.read_namespace(namespace)
    return True
  except client.exceptions.ApiException:
    return False


def secret_exists(*, secretname, namespace):
  try:
    K8S.read_namespaced_secret(secretname, namespace)
    return True
  except client.exceptions.ApiException:
    return False


def serviceaccount_has_secret(*, secretname, serviceaccount):
  for imagepullsecret in serviceaccount.image_pull_secrets:
    if imagepullsecret.name == secretname:
      return True
  return False


def delete_imagepullbackoff_pods(*, myconfig):
  for ns in myconfig["namespaces"]:
    if namespace_exists(namespace=ns):
      for pod in K8S.list_namespaced_pod(ns).items:
        if pod.status.init_container_statuses:
          for stats in pod.status.init_container_statuses:
            if stats.state.waiting:
              if stats.state.waiting.reason == "ImagePullBackOff" or stats.state.waiting.reason == "ErrImagePull":
                K8S.delete_namespaced_pod(pod.metadata.name, ns)
                print(f"Deleted ImagePullBackOff pod '{pod.metadata.name}' in namespace '{ns}'")
        for stats in pod.status.container_statuses:
          if stats.state.waiting:
            if stats.state.waiting.reason == "ImagePullBackOff" or stats.state.waiting.reason == "ErrImagePull":
              K8S.delete_namespaced_pod(pod.metadata.name, ns)
              print(f"Deleted ImagePullBackOff pod '{pod.metadata.name}' in namespace '{ns}'")


def main(argv):
  print("Patcher started")
  parser = argparse.ArgumentParser()
  parser.add_argument('--configfile', type=str, required=True)

  args = parser.parse_args()
  cfile = args.configfile
  pconf = parse_config(file=cfile)
  runtime = pconf["time"]["runtime"]
  interval = pconf["time"]["interval"]

  try:
    config.load_incluster_config()
  except config.ConfigException:
    try:
      config.load_kube_config()
    except config.ConfigException:
      raise Exception("Could not configure kubernetes python client")

  global K8S
  K8S = client.CoreV1Api()

  if runtime == 0 :
    while True:
      patch(myconfig=pconf)
      delete_imagepullbackoff_pods(myconfig=pconf)
      sleep(int(interval))
  else:
    start_time = time()
    while int(time() - start_time) < int(runtime):
      patch(myconfig=pconf)
      delete_imagepullbackoff_pods(myconfig=pconf)
      sleep(int(interval))

  print(f"Patcher finished after {int(time() - start_time)} seconds")
  exit(0)

if __name__ == "__main__":
  main(sys.argv[1:])
