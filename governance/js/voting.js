// MEMES 24H Governance - Vote Submission
// Votes are submitted via GitHub Issues and processed by GitHub Actions

import { CONFIG } from './config.js';
import { getAddress, signVote } from './wallet.js';
import { resolveIdentity, formatTDH } from './api6529.js';

// Submit a vote on a proposal
export async function submitVote(proposalId, vote) {
  if (vote !== 'yes' && vote !== 'no') {
    throw new Error('Vote must be "yes" or "no"');
  }

  const address = getAddress();
  if (!address) throw new Error('Wallet not connected');

  // Get identity and TDH
  const identity = await resolveIdentity(address);
  if (identity.tdh === 0) {
    throw new Error('You need TDH to vote. Collect The Memes NFTs to earn TDH.');
  }

  // Sign the vote
  const { signature, timestamp } = await signVote(proposalId, vote);

  const voteData = {
    proposalId,
    vote,
    voter: identity.primaryAddress,
    voterHandle: identity.handle,
    voterTDH: identity.tdh,
    timestamp,
    signature,
    submittedBy: address // original connected wallet (may be delegate)
  };

  // Submit as GitHub Issue
  const title = `[VOTE] ${proposalId} ${vote}`;
  const body = '```json\n' + JSON.stringify(voteData, null, 2) + '\n```';
  const issueUrl = `https://github.com/${CONFIG.REPO_OWNER}/${CONFIG.REPO_NAME}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}&labels=vote`;

  window.open(issueUrl, '_blank');

  return voteData;
}
