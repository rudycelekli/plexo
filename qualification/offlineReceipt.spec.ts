import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { test, expect, BLOCK, NETWORKS } from './fixtures'

test('qualification records an actual offline download', async ({ plexo, serve, dirs }) => {
  const header = 'attachment; filename = "quarterly report.csv"'
  const origin = await serve({ size: 3 * BLOCK, contentDisposition: header })
  const url = origin.url()
  expect(new URL(url).hostname).toBe('127.0.0.1')
  const preview = await plexo.api.probeUrl(url)
  await plexo.start(url, origin.sha256)
  const state = await plexo.waitForHttpStatus('completed')
  const versions = await plexo.electronApp.evaluate(() => process.versions)
  await writeFile(join(process.env.PLEXO_QUALIFICATION_PROOF!, 'offline-download.json'), JSON.stringify({
    url, header, bytes: 3 * BLOCK, sha256: origin.sha256, networks: NETWORKS,
    preview, fileName: state.fileName, destinationPath: state.destinationPath,
    isolatedDirs: dirs, versions
  }, null, 2))
  expect(state.destinationPath.startsWith(dirs.dest)).toBe(true)
})
