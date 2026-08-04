# Custom ComfyUI Services

A service is a parameter contract: every workflow in it answers the same
parameters, and the run form renders that contract. The workflow dropdown is
the selection; a package's models are variants of its graph. When you want a
different parameter set (a basic form, an advanced form, no presets), you
create a new service by uploading your own provider.

## Fork the provider

1. Copy the shs comfyui provider JSON (from the community catalog:
   `providers/shs/comfyui.json`). The license permits forking shs content;
   ship it under your own namespace and name.
2. Rename `slug` (e.g. `acme/comfyui-lab`) and the service ids under
   `services`. Service ids are yours; the worker treats them as data.
3. Define each service's `parameter_schema`: this is the contract your
   packages must fit. Do not declare a `model` or `package` property; the
   workflow dropdown is maintained automatically from installed packages.
4. Set each service's queue. Queues are a pre-registered allowlist: use an
   existing queue (`comfyui_image_jobs`) or have the operator widen the
   allowlist with `SHS_ALLOWED_QUEUES` first. A provider upload can never
   widen the set itself.
5. Upload the provider (Providers, Upload Provider; super-admin).

## Add workflows to your service

Package your graphs as single-file ComfyUI packages whose `service.id` names
your service. At upload the package is schema-validated and checked against
the service contract:

- its `parameters` must be a subset of the contract's properties (a package
  declaring parameters the service does not offer is refused, named);
- the contract's required parameters must be declared;
- per-package bounds still live in the manifest and are enforced by the
  worker at run time.

Uploads land private; publish them from the ComfyUI marketplace's Custom tab
when ready. Model files remain the operator's job: `required_models` in the
package is the app-to-operator handoff.

## Serving a custom queue

If your services declare their own queue, the operator points a worker at it:

    SHS_ALLOWED_QUEUES=comfyui_lab_jobs        # api side, widens the allowlist
    studio-workers run --type comfyui-image --queues comfyui_lab_jobs,comfyui_image_jobs

The workers page shows which queues each worker serves and warns when an
installed service's queue has no live worker.

## Terms

Your forked provider and packages are your content under your responsibility;
see LEGAL.md for the license terms that apply to redistributed shs content.
