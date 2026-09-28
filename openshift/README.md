# Deploying `boleteria` to the OpenShift Developer Sandbox (manual)

The image is on Docker Hub: `docker.io/luisrro21/jfc-boleteria:<version>`
(built and pushed by `scripts/docker-publish.sh <version>`).

Two files from this folder, each pasted into **+ → Import YAML → Create**, in this order:

| File | What it is |
|---|---|
| `secret.yaml` | Secret `boleteria-config`: database connection, gateway secret, QR key. **Gitignored — never commit or share it.** (Same values as `secret.env`, for `oc`.) |
| `boleteria.yaml` | Deployment (2 replicas of the Docker Hub image, health probes), Service and Route (public HTTPS URL that API Gateway calls) |

## 1. Secret

```bash
pbcopy < openshift/secret.yaml
```

Console: **+ → Import YAML** → paste → **Create**.

## 2. Deployment, Service and Route

```bash
pbcopy < openshift/boleteria.yaml
```

Console: **+ → Import YAML** → paste → **Create** (it creates all three resources).

With `oc` instead (after *Copy login command* → `oc login …`):

```bash
oc apply -f openshift/secret.yaml -f openshift/boleteria.yaml
```

## 3. Check it's running

- **Topology** view: the `boleteria` ring turns dark blue with **2 pods**, both *Running* and *Ready*
  (Ready = each pod loaded the 46,400-seat map from RDS; takes a few seconds).
- One pod's **Logs** shows `es ahora el líder del expirador` — that pod runs the expiry worker.
- **Routes** → `boleteria` → copy the **Location** URL
  (`https://boleteria-<project>.apps.<cluster>.openshiftapps.com`) and send it to Claude.

Opening that URL + `/healthz` in a browser should show `{"ok": true, ...}`.
Any `/boleteria/...` URL opened directly answers **403** — correct: only API Gateway has the secret.

## Updating to a new image version

Deployment `boleteria` → **Actions → Edit Deployment** → change the image tag → **Save**, or:

```bash
oc set image deployment/boleteria boleteria=docker.io/luisrro21/jfc-boleteria:1.0.1
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ErrImagePull` / `toomanyrequests` | Docker Hub limits anonymous pulls and the Sandbox shares IPs. Create a pull secret with a **read-only** Docker Hub token: `oc create secret docker-registry dockerhub --docker-server=docker.io --docker-username=luisrro21 --docker-password=<token>` then `oc secrets link default dockerhub --for=pull`, and delete the failing pod. |
| Pods Running but not Ready | RDS is stopped or unreachable. `scripts/rds.sh start` on your Mac; the pods retry on their own. |
| App scaled to 0 after some hours | The Sandbox idles inactive apps. Scale back to 2 in the console (or `oc scale deployment/boleteria --replicas=2`) ~5 min before the demo. |
