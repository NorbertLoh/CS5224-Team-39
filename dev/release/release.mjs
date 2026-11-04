import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const services = ['identity', 'tenant', 'scheduling', 'consultation', 'clinical_records', 'billing', 'document', 'fulfilment', 'notification']
export const images = [
  ...services.map(name => ({ name, platform: 'linux/amd64', context: `services/${name}`, file: 'Dockerfile', shared: true })),
  { name: 'signalling', platform: 'linux/amd64', context: 'services/signalling', file: 'Dockerfile' },
  ...['document', 'notification'].map(name => ({ name: `${name}-lambda`, platform: 'linux/amd64', context: '.', file: `services/${name}/Dockerfile.lambda`, shared: true })),
]
export const frontendKeys = ['VITE_USE_AWS', 'VITE_AWS_API_BASE_URL', 'VITE_AWS_COGNITO_CLIENT_ID', 'VITE_AWS_COGNITO_ISSUER', 'VITE_AWS_COGNITO_OAUTH_BASE_URL', 'VITE_AWS_COGNITO_API_URL']

function run(command, args, capture = false) {
  const result = spawnSync(command, args, { cwd: root, encoding: 'utf8', stdio: capture ? ['ignore', 'pipe', 'inherit'] : 'inherit' })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${command} exited ${result.status}`)
  return result.stdout?.trim()
}
function json(path) { return JSON.parse(readFileSync(resolve(root, path), 'utf8').replace(/^\uFEFF/, '')) }
function save(path, value) { writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`) }
export function platformOutput(value) {
  const output = value.platform?.value ?? value.demo?.value ?? value
  if (!output.repositories || !output.frontend_environment) throw new Error('Expected Terraform output -json or the platform output value')
  return output
}
export function frontendConfig(value) {
  const config = value.frontend_environment ?? value
  if (Object.keys(config).some(key => !frontendKeys.includes(key))) throw new Error('Only the six public frontend environment keys are accepted')
  if (frontendKeys.some(key => typeof config[key] !== 'string' || !config[key])) throw new Error('All six frontend settings are required')
  if (config.VITE_USE_AWS !== 'true') throw new Error('Release frontend requires VITE_USE_AWS=true')
  for (const key of frontendKeys.filter(key => key.endsWith('URL') || key.endsWith('ISSUER'))) {
    const url = new URL(config[key])
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error(`${key} requires a public HTTPS URL without credentials, query or fragment`)
  }
  return config
}
export function buildArgs(image, tag) {
  const args = ['buildx', 'build', '--platform', image.platform, '--provenance=false', '--load', '--tag', tag, '--label', `org.opencontainers.image.revision=${tag.split(':').at(-1)}`]
  if (image.shared) args.push('--build-context', `python_common=${resolve(root, 'packages/python_common')}`)
  return [...args, '--file', resolve(root, image.context, image.file), resolve(root, image.context)]
}

export function main(args) {
  const [command, ...rest] = args
  const docker = process.env.RELEASE_DOCKER || 'docker'
  const revision = run('git', ['rev-parse', 'HEAD'], true)
  const output = resolve(root, '.local/releases', revision)
  if (command === 'inventory') {
    console.log(JSON.stringify(images, null, 2))
    return
  }
  if (!['build', 'frontend', 'pin'].includes(command)) throw new Error('Usage: node dev/release/release.mjs inventory | build [image ...] | frontend <public-config.json> | pin <terraform-output.json>')
  if (run('git', ['status', '--porcelain', '--untracked-files=normal'], true)) throw new Error('Commit source changes before creating a revision-tagged release')
  mkdirSync(output, { recursive: true })
  if (command === 'build') {
    const selected = rest.length ? rest.map(name => {
      const image = images.find(image => image.name === name)
      if (!image) throw new Error(`Unknown release image: ${name}`)
      return image
    }) : images
    for (const image of selected) {
      const tag = `telelink-release/${image.name}:${revision}`
      run(docker, buildArgs(image, tag))
      const info = JSON.parse(run(docker, ['image', 'inspect', tag], true))[0]
      if (`${info.Os}/${info.Architecture}` !== image.platform) throw new Error(`Wrong platform for ${tag}`)
      save(resolve(output, `${image.name}.json`), { ...image, tag, revision, imageId: info.Id })
    }
    console.log(`Local images and metadata ready: ${output}`)
  } else if (command === 'frontend') {
    if (rest.length !== 1) throw new Error('Provide a public frontend configuration JSON file')
    const value = json(rest[0])
    const config = frontendConfig(value.platform || value.demo ? platformOutput(value) : value)
    const configHash = createHash('sha256').update(JSON.stringify(config)).digest('hex').slice(0, 16)
    const destination = resolve(output, `frontend-${configHash}`)
    const build = ['buildx', 'build', '--platform', 'linux/amd64', '--build-context', `contracts=${resolve(root, 'contracts')}`, '--file', resolve(root, 'apps/web/Dockerfile.release'), '--target', 'export', '--output', `type=local,dest=${destination}`]
    for (const [key, value] of Object.entries(config)) build.push('--build-arg', `${key}=${value}`)
    run(docker, [...build, resolve(root, 'apps/web')])
    if (!readFileSync(resolve(destination, 'index.html'), 'utf8').includes('/assets/')) throw new Error('Missing built frontend assets')
    save(resolve(output, `frontend-${configHash}.json`), { revision, config, directory: destination })
    console.log(`Static frontend ready: ${destination}`)
  } else {
    if (rest.length !== 1) throw new Error('Provide Terraform output JSON from the selected environment')
    const platform = platformOutput(json(rest[0]))
    if (platform.cpu_architecture !== 'X86_64') throw new Error('This AMD64 release requires Terraform cpu_architecture=X86_64; refresh the selected environment outputs')
    const pinned = {}
    for (const image of images) {
      const repository = platform.repositories[image.name]
      if (typeof repository !== 'string' || !/^\d{12}\.dkr\.ecr\.ap-southeast-1\.amazonaws\.com\/[a-z0-9/_-]+$/.test(repository)) throw new Error(`Invalid Singapore ECR repository for ${image.name}`)
      const tag = `${repository}:${revision}`
      // Inspect the registry, not a local image ID. Requires a separate operator push.
      const manifest = run(docker, ['buildx', 'imagetools', 'inspect', tag, '--raw'], true)
      const parsed = JSON.parse(manifest)
      if (parsed.manifests) throw new Error(`Expected a single-platform image for ${image.name}`)
      const info = JSON.parse(run(docker, ['buildx', 'imagetools', 'inspect', tag, '--format', '{{json .Image}}'], true))
      if (`${info.os}/${info.architecture}` !== image.platform) throw new Error(`Registry platform mismatch for ${image.name}`)
      // Fetch the registry digest directly; hashing pretty-printed JSON is incorrect.
      const detail = run(docker, ['buildx', 'imagetools', 'inspect', tag], true)
      const digest = detail.match(/^Digest:\s+(sha256:[a-f0-9]{64})\s*$/m)?.[1]
      if (!digest) throw new Error(`Missing registry digest for ${image.name}`)
      pinned[image.name] = `${repository}@${digest}`
    }
    save(resolve(output, 'images.tfvars.json'), { images: pinned, enable_workloads: false })
    console.log(`Digest-pinned inputs ready: ${output}/images.tfvars.json (workloads disabled)`)
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)) } catch (error) { console.error(error.message); process.exitCode = 1 }
}
