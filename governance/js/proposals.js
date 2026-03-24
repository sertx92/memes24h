// MEMES 24H Governance - Proposals Management
// Read proposals from GitHub, create new ones via Issues

import { CONFIG, GITHUB_RAW, GITHUB_API } from './config.js';
import { resolveIdentity, getTDH, verifyWave, formatTDH } from './api6529.js';
import { getAddress, signProposal } from './wallet.js';

let proposalsCache = null;
let proposalsCacheTs = 0;

// Fetch all proposals from the GitHub repo
export async function listProposals() {
  if (proposalsCache && Date.now() - proposalsCacheTs < CONFIG.CACHE_PROPOSALS_TTL) {
    return proposalsCache;
  }

  try {
    const res = await fetch(`${GITHUB_API}/contents/${CONFIG.PROPOSALS_PATH}`);
    if (!res.ok) return [];

    const files = await res.json();
    const jsonFiles = files.filter(f => f.name.endsWith('.json'));

    const proposals = await Promise.all(
      jsonFiles.map(async (f) => {
        const r = await fetch(f.download_url);
        return r.json();
      })
    );

    // Sort: active first, then by creation date desc
    proposals.sort((a, b) => {
      if (a.status === 'active' && b.status !== 'active') return -1;
      if (a.status !== 'active' && b.status === 'active') return 1;
      return new Date(b.createdAt) - new Date(a.createdAt);
    });

    proposalsCache = proposals;
    proposalsCacheTs = Date.now();
    return proposals;
  } catch (err) {
    console.error('Failed to list proposals:', err);
    return [];
  }
}

// Fetch a single proposal
export async function getProposal(id) {
  try {
    const res = await fetch(`${GITHUB_RAW}/${CONFIG.PROPOSALS_PATH}/${id}.json?t=${Date.now()}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// Get votes for a proposal
export async function getProposalVotes(proposalId) {
  try {
    const res = await fetch(`${GITHUB_API}/contents/${CONFIG.VOTES_PATH}/${proposalId}`);
    if (!res.ok) return [];

    const files = await res.json();
    const jsonFiles = files.filter(f => f.name.endsWith('.json'));

    const votes = await Promise.all(
      jsonFiles.map(async (f) => {
        const r = await fetch(f.download_url);
        return r.json();
      })
    );

    return votes;
  } catch {
    return [];
  }
}

// Tally votes with live TDH lookup
export async function tallyVotes(votes) {
  let yesTDH = 0;
  let noTDH = 0;
  let yesCount = 0;
  let noCount = 0;

  const detailed = await Promise.all(
    votes.map(async (v) => {
      const currentTDH = await getTDH(v.voter);
      return { ...v, currentTDH };
    })
  );

  for (const v of detailed) {
    if (v.vote === 'yes') {
      yesTDH += v.currentTDH;
      yesCount++;
    } else {
      noTDH += v.currentTDH;
      noCount++;
    }
  }

  return {
    yesTDH, noTDH, yesCount, noCount,
    totalTDH: yesTDH + noTDH,
    passed: yesTDH >= CONFIG.TDH_THRESHOLD_PASS,
    progress: Math.min(100, (yesTDH / CONFIG.TDH_THRESHOLD_PASS) * 100),
    votes: detailed
  };
}

// Create a new proposal (submits via GitHub Issue)
export async function createProposal(action, waveId, reason) {
  const address = getAddress();
  if (!address) throw new Error('Wallet not connected');

  // Verify TDH
  const identity = await resolveIdentity(address);
  if (identity.tdh < CONFIG.MIN_TDH_PROPOSE) {
    throw new Error(`Insufficient TDH. You have ${formatTDH(identity.tdh)}, need ${formatTDH(CONFIG.MIN_TDH_PROPOSE)}.`);
  }

  // Verify wave exists
  const wave = await verifyWave(waveId);
  if (!wave.exists) throw new Error('Wave not found on 6529.');

  // Sign the proposal
  const { signature, timestamp } = await signProposal(action, waveId, wave.name, reason);

  const expiresAt = new Date(timestamp * 1000 + CONFIG.PROPOSAL_DURATION_DAYS * 86400000).toISOString();

  const proposal = {
    id: `prop-${timestamp}`,
    action,
    waveId,
    waveName: wave.name,
    proposer: {
      address: identity.primaryAddress,
      handle: identity.handle,
      tdh: identity.tdh
    },
    reason,
    createdAt: new Date(timestamp * 1000).toISOString(),
    expiresAt,
    status: 'active',
    signature
  };

  // Submit as GitHub Issue
  // The user will be redirected to create the issue
  const title = `[PROPOSAL] ${action} wave: ${wave.name}`;
  const body = '```json\n' + JSON.stringify(proposal, null, 2) + '\n```';
  const issueUrl = `https://github.com/${CONFIG.REPO_OWNER}/${CONFIG.REPO_NAME}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}&labels=proposal`;

  window.open(issueUrl, '_blank');

  // Invalidate cache
  proposalsCache = null;

  return proposal;
}

// Check if current user has voted on a proposal
export async function hasVoted(proposalId) {
  const address = getAddress();
  if (!address) return false;

  const identity = await resolveIdentity(address);
  const primaryAddr = identity.primaryAddress.toLowerCase();

  try {
    const res = await fetch(`${GITHUB_RAW}/${CONFIG.VOTES_PATH}/${proposalId}/${primaryAddr}.json?t=${Date.now()}`);
    return res.ok;
  } catch {
    return false;
  }
}
