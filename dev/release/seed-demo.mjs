import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const [path] = process.argv.slice(2)
let demo
if (path) {
  const { platform, environment } = JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, ''))
  if (environment?.value !== 'demo') throw new Error('Expected Terraform outputs from the demo root')
  demo = platform?.value
} else if (process.env.TELELINK_DEMO_SEED) {
  demo = JSON.parse(process.env.TELELINK_DEMO_SEED)
}

if (!demo?.demo_seed_task || !demo.demo_login_secret) {
  throw new Error('Usage: node dev/release/seed-demo.mjs <demo Terraform output JSON>')
}

function aws(args, wait = false) {
  const result = spawnSync(process.env.RELEASE_AWS || 'aws', [
    ...args, '--region', 'ap-southeast-1', '--no-cli-pager', '--output', 'json',
  ], { encoding: 'utf8' })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(result.stderr.trim())
  if (!wait) return JSON.parse(result.stdout)
}

const started = aws(['ecs', 'run-task', '--cli-input-json', JSON.stringify({
  cluster: demo.cluster_name,
  taskDefinition: demo.demo_seed_task,
  launchType: 'FARGATE',
  platformVersion: '1.4.0',
  networkConfiguration: demo.task_network_configuration,
  startedBy: 'demo-account-seed',
})])
if (started.failures?.length || started.tasks?.length !== 1) throw new Error('Demo seed task could not start')
const task = started.tasks[0].taskArn
console.log(`Waiting for demo seed task ${task.split('/').at(-1)}`)
aws(['ecs', 'wait', 'tasks-stopped', '--cluster', demo.cluster_name, '--tasks', task], true)
const stopped = aws(['ecs', 'describe-tasks', '--cluster', demo.cluster_name, '--tasks', task]).tasks[0]
if (stopped?.containers?.length !== 1 || stopped.containers[0].exitCode !== 0) {
  throw new Error('Demo seed failed. Check the document CloudWatch log stream for this task.')
}
console.log(`Demo accounts ready. Operator credentials are in Secrets Manager at ${demo.demo_login_secret}.`)
