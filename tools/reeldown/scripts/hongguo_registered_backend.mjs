#!/usr/bin/env node
// Bridge a caller-reviewed source module to ReelDown's external backend contract.
// Signing, registration and optional media processing stay in that external module.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {execFileSync} from 'node:child_process';
import {createInterface} from 'node:readline';

const DOMAINS = ['qznovelvod.com', 'fqnovelvod.com', 'douyinvod.com', 'bdcgslb.com',
  'vegslb.com', 'v.smtcdns.com', 'free-lbv6.idouyinvod.com', 'gslb.queniudt.cn'];
const CODECS = new Set(['h264', 'avc', 'avc1', 'hevc', 'h265', 'hvc1', 'hev1', 'bytevc1']);
const SAFE_ERRORS = new Set(['INVALID_CONFIG', 'INVALID_EPISODE', 'DESTINATION_EXISTS', 'WORKER_ACTIVE',
  'SOURCE_MODULE_INVALID', 'SOURCE_UNAVAILABLE', 'DEVICE_REGISTRATION_FAILED', 'EMPTY_RESPONSE',
  'INVALID_RESPONSE', 'BUSINESS_REJECTED', 'SECURITY_BLOCKED', 'MISSING_MODEL', 'QUALITY_UNAVAILABLE',
  'NO_COMPATIBLE_SOURCE', 'EPISODE_MISMATCH', 'MODEL_DURATION_REQUIRED', 'MODEL_SIZE_INVALID',
  'MEDIA_ORIGIN_INVALID', 'MEDIA_REDIRECT_LIMIT', 'MEDIA_HTTP_FAILED', 'MEDIA_SIZE_MISMATCH',
  'MEDIA_FORMAT_INVALID', 'MEDIA_INVALID', 'MEDIA_PROCESSOR_REQUIRED', 'MEDIA_KEY_INVALID',
  'ETIMEDOUT', 'ECONNABORTED', 'ENOTFOUND', 'EAI_AGAIN', 'ECONNRESET', 'ECONNREFUSED',
  'EHOSTUNREACH', 'ENETUNREACH', 'EPIPE', 'ERR_CANCELED', 'ERR_NETWORK']);
const fail = code => Object.assign(new Error(code), {code});
function checkEpisode(id) {
  if (typeof id !== 'string' || !/^[0-9]{10,30}$/.test(id)) throw fail('INVALID_EPISODE');
}
function mediaUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw fail('MEDIA_ORIGIN_INVALID'); }
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443') ||
      !DOMAINS.some(d => url.hostname === d || url.hostname.endsWith('.' + d))) throw fail('MEDIA_ORIGIN_INVALID');
  return url;
}

export function validateSource(source, episodeId) {
  checkEpisode(episodeId);
  if (!source || source.vid !== episodeId) throw fail('EPISODE_MISMATCH');
  if (!CODECS.has(String(source.codec).toLowerCase())) throw fail('NO_COMPATIBLE_SOURCE');
  if (typeof source.duration !== 'number' || !Number.isFinite(source.duration) ||
      source.duration <= 0 || source.duration > 86400) throw fail('MODEL_DURATION_REQUIRED');
  if (source.size != null && (!Number.isSafeInteger(source.size) || source.size < 0)) throw fail('MODEL_SIZE_INVALID');
  if (source.contentKey != null && !/^[0-9a-f]{32}$/i.test(source.contentKey)) throw fail('MEDIA_KEY_INVALID');
  mediaUrl(source.url);
  return source;
}

export async function loadConfig(filename) {
  const base = path.dirname(path.resolve(filename));
  const config = JSON.parse(fs.readFileSync(filename, 'utf8'));
  if (!config || typeof config.resolver_module !== 'string' || !config.resolver_module ||
      !['auto', '1080p', '720p'].includes(config.quality ?? 'auto')) throw fail('INVALID_CONFIG');
  const resolver = await import(pathToFileURL(path.resolve(base, config.resolver_module)));
  const api = resolver.default ?? resolver;
  if (typeof api.fetchAppPlayUrl !== 'function') throw fail('SOURCE_MODULE_INVALID');
  let processor;
  if (config.media_module != null) {
    if (typeof config.media_module !== 'string' || !config.media_module) throw fail('INVALID_CONFIG');
    const imported = await import(pathToFileURL(path.resolve(base, config.media_module)));
    processor = imported.default ?? imported;
    if (typeof processor.decryptMp4File !== 'function') throw fail('SOURCE_MODULE_INVALID');
  }
  return {
    resolve: id => api.fetchAppPlayUrl(id, {quality: config.quality ?? 'auto'}),
    processMedia: processor ? (input, output, key) => processor.decryptMp4File(input, output, key) : null,
    ffprobe: config.ffprobe ?? 'ffprobe', ffmpeg: config.ffmpeg ?? 'ffmpeg',
  };
}

async function resolveSelected(options, episodeId) {
  // The reviewed resolver owns registration and its one alternate attempt.
  // Never multiply its retry budget by wrapping it in another resolver loop.
  const result = await options.resolve(episodeId);
  if (!result || result.vid !== episodeId) throw fail('EPISODE_MISMATCH');
  const rows = Array.isArray(result.variants) && result.variants.length ? result.variants : [result];
  const selected = rows.find(r => CODECS.has(String(r?.codec).toLowerCase()));
  if (!selected) throw fail('NO_COMPATIBLE_SOURCE');
  return validateSource(selected, episodeId);
}

export async function probe(options, episodeId) {
  checkEpisode(episodeId);
  const source = await resolveSelected(options, episodeId);
  return {available: true, probe_only: true, episode_id: episodeId,
    expected_duration: source.duration, model_bytes: source.size || null,
    codec: String(source.codec), encrypted: source.contentKey != null};
}

async function transfer(source, filename, fetchImpl) {
  let url = mediaUrl(source.url);
  const signal = AbortSignal.timeout(180000);
  for (let hops = 0; hops < 4; hops++) {
    // Only the media UA is forwarded; API signatures and account headers never are.
    const response = await fetchImpl(url, {headers: typeof source.userAgent === 'string'
      ? {'User-Agent': source.userAgent} : {}, redirect: 'manual', signal});
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location');
      await response.body?.cancel();
      if (!location) throw fail('MEDIA_ORIGIN_INVALID');
      url = mediaUrl(new URL(location, url).href);
      continue;
    }
    if (!response.ok || !response.body) {
      await response.body?.cancel();
      throw fail('MEDIA_HTTP_FAILED');
    }
    const length = response.headers.get('content-length');
    const expected = length == null ? null : Number(length);
    if (expected != null && (!Number.isSafeInteger(expected) || expected <= 0 ||
        (source.size > 0 && source.size !== expected))) {
      await response.body.cancel();
      throw fail('MEDIA_SIZE_MISMATCH');
    }
    await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(filename, {flags: 'wx', mode: 0o600}));
    const bytes = fs.statSync(filename).size;
    if (!bytes || (source.size > 0 && bytes !== source.size) || (expected != null && bytes !== expected))
      throw fail('MEDIA_SIZE_MISMATCH');
    const fd = fs.openSync(filename, 'r');
    const header = Buffer.alloc(16);
    try { fs.readSync(fd, header, 0, header.length, 0); } finally { fs.closeSync(fd); }
    if (header.toString('ascii', 4, 8) !== 'ftyp') throw fail('MEDIA_FORMAT_INVALID');
    return;
  }
  throw fail('MEDIA_REDIRECT_LIMIT');
}

async function sha256(filename) {
  const hash = createHash('sha256');
  for await (const block of fs.createReadStream(filename)) hash.update(block);
  return hash.digest('hex');
}

export async function download(options, episodeId, output) {
  checkEpisode(episodeId);
  const destination = path.resolve(output);
  const receipt = destination + '.verification.json';
  if (fs.existsSync(destination) || fs.existsSync(receipt)) throw fail('DESTINATION_EXISTS');
  fs.mkdirSync(path.dirname(destination), {recursive: true});
  const lock = destination + '.reeldown.lock';
  let lockFd;
  try { lockFd = fs.openSync(lock, 'wx', 0o600); } catch (error) {
    if (error.code === 'EEXIST') throw fail('WORKER_ACTIVE');
    throw error;
  }
  fs.closeSync(lockFd);
  let staging, receiptOwned = false, published = false;
  let stage = 'source';
  try {
    const source = await resolveSelected(options, episodeId);
    if (source.contentKey != null && !options.processMedia) throw fail('MEDIA_PROCESSOR_REQUIRED');
    staging = fs.mkdtempSync(path.join(path.dirname(destination), '.reeldown-'));
    const incoming = path.join(staging, 'incoming.mp4');
    const clear = path.join(staging, 'verified.mp4');
    stage = 'transfer';
    await transfer(source, incoming, options.fetch ?? globalThis.fetch);
    stage = 'media';
    if (source.contentKey != null) await options.processMedia(incoming, clear, Buffer.from(source.contentKey, 'hex'));
    else fs.renameSync(incoming, clear);
    stage = 'verification';
    const parsed = JSON.parse(execFileSync(options.ffprobe ?? 'ffprobe', ['-v', 'error', '-f', 'mov',
      '-show_entries', 'format=duration:stream=codec_type,codec_name,codec_tag_string,width,height', '-of', 'json', clear],
    {encoding: 'utf8', timeout: 30000, stdio: ['ignore', 'pipe', 'ignore']}));
    const video = parsed.streams?.find(s => s.codec_type === 'video');
    const duration = Number(parsed.format?.duration);
    if (!video || !['h264', 'hevc'].includes(video.codec_name) ||
        parsed.streams.some(s => ['encv', 'enca'].includes(s.codec_tag_string)) || !Number.isFinite(duration) ||
        Math.abs(duration - source.duration) > Math.max(2, source.duration * .02)) throw fail('MEDIA_INVALID');
    execFileSync(options.ffmpeg ?? 'ffmpeg', ['-v', 'error', '-xerror', '-nostdin', '-f', 'mov', '-i', clear,
      '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'],
    {timeout: 300000, stdio: ['ignore', 'ignore', 'ignore']});
    const result = {success: true, episode_id: episodeId, bytes: fs.statSync(clear).size,
      sha256: await sha256(clear), expected_duration: source.duration, duration_seconds: duration,
      codec: video.codec_name, width: video.width, height: video.height,
      full_decode_verified: true, source_kind: 'registered_client'};
    stage = 'publication';
    fs.writeFileSync(receipt, JSON.stringify(result) + '\n', {flag: 'wx', mode: 0o600});
    receiptOwned = true;
    fs.linkSync(clear, destination); // Atomic, and refuses an existing destination.
    published = true;
    return result;
  } catch (error) {
    error.reeldownStage = stage;
    throw error;
  } finally {
    if (staging) fs.rmSync(staging, {recursive: true, force: true});
    if (receiptOwned && !published) fs.unlinkSync(receipt);
    fs.unlinkSync(lock);
  }
}

export function safeError(error) {
  return {error: SAFE_ERRORS.has(error?.code) ? error.code : 'REGISTERED_BACKEND_FAILED',
    stage: ['source', 'transfer', 'media', 'verification', 'publication'].includes(error?.reeldownStage)
      ? error.reeldownStage : 'configuration_or_source'};
}

async function main(argv) {
  const isProbe = argv[2] === '--probe';
  try {
    if (argv[0] === '--config' && argv.length === 3 && argv[2] === '--serve') {
      const options = await loadConfig(argv[1]);
      const input = createInterface({input: process.stdin, crlfDelay: Infinity});
      for await (const line of input) {
        let request;
        try {
          if (Buffer.byteLength(line) > 8192) throw fail('INVALID_CONFIG');
          request = JSON.parse(line);
          if (!Number.isSafeInteger(request.request_id) || request.request_id < 1 || typeof request.output !== 'string') throw fail('INVALID_CONFIG');
          checkEpisode(request.episode_id);
          const result = await download(options, request.episode_id, request.output);
          process.stdout.write(JSON.stringify({...result, request_id: request.request_id}) + '\n');
        } catch (error) {
          process.stdout.write(JSON.stringify({success: false, ...safeError(error), request_id: request?.request_id ?? null}) + '\n');
        }
      }
      return;
    }
    if (argv[0] !== '--config' || argv.length !== 4) throw fail('INVALID_CONFIG');
    const episodeId = isProbe ? argv[3] : argv[2];
    checkEpisode(episodeId);
    const options = await loadConfig(argv[1]);
    const result = isProbe ? await probe(options, episodeId) : await download(options, episodeId, argv[3]);
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify(isProbe
      ? {available: false, probe_only: true, ...safeError(error)}
      : {success: false, ...safeError(error)}) + '\n');
    process.exitCode = 1;
  }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main(process.argv.slice(2));
