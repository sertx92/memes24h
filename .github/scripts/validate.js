// MEMES 24H Governance - Vote/Proposal Validator
// Runs in GitHub Actions to validate EIP-712 signatures and TDH
// Usage: node validate.js <issue-number>

const { ethers } = require('ethers');
const fs = require('fs');
const path = require('path');

const API_6529 = 'https://api.6529.io/api';
const MIN_TDH_PROPOSE = 1_000_000;

const EIP712_DOMAIN = {
  name: 'MEMES24H Governance',
  version: '1',
  chainId: 1
};

const EIP712_TYPES = {
  Proposal: [
    { name: 'action', type: 'string' },
    { name: 'waveId', type: 'string' },
    { name: 'waveName', type: 'string' },
    { name: 'reason', type: 'string' },
    { name: 'timestamp', type: 'uint256' }
  ],
  Vote: [
    { name: 'proposalId', type: 'string' },
    { name: 'vote', type: 'string' },
    { name: 'timestamp', type: 'uint256' }
  ]
};

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${url}`);
  return res.json();
}

async function getTDH(address) {
  const data = await fetchJSON(`${API_6529}/profiles/${address}`);
  return data.consolidation?.tdh || 0;
}

async function resolveConsolidation(address) {
  const data = await fetchJSON(`${API_6529}/profiles/${address}`);
  return data.consolidation?.consolidation_key || address;
}

async function processProposal(data) {
  console.log('Processing proposal:', data.id);

  // Verify signature
  const message = {
    action: data.action,
    waveId: data.waveId,
    waveName: data.waveName,
    reason: data.reason,
    timestamp: data.createdAt ? Math.floor(new Date(data.createdAt).getTime() / 1000) : 0
  };

  // Find timestamp from the data
  if (data.signature) {
    // For proposals, we trust the signed data but verify the signer
    const recoveredAddr = ethers.verifyTypedData(
      EIP712_DOMAIN,
      { Proposal: EIP712_TYPES.Proposal },
      message,
      data.signature
    );

    const resolvedAddr = await resolveConsolidation(recoveredAddr.toLowerCase());
    console.log(`Signer: ${recoveredAddr}, Resolved: ${resolvedAddr}`);

    // Verify TDH
    const tdh = await getTDH(recoveredAddr.toLowerCase());
    console.log(`TDH: ${tdh}`);

    if (tdh < MIN_TDH_PROPOSE) {
      throw new Error(`Insufficient TDH: ${tdh} < ${MIN_TDH_PROPOSE}`);
    }

    // Write proposal file
    const filePath = path.join('data', 'proposals', `${data.id}.json`);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
    console.log(`Written: ${filePath}`);

    return { success: true, file: filePath };
  }

  throw new Error('No signature found');
}

async function processVote(data) {
  console.log('Processing vote:', data.proposalId, data.vote);

  // Verify signature
  const message = {
    proposalId: data.proposalId,
    vote: data.vote,
    timestamp: data.timestamp
  };

  const recoveredAddr = ethers.verifyTypedData(
    EIP712_DOMAIN,
    { Vote: EIP712_TYPES.Vote },
    message,
    data.signature
  );

  console.log(`Signer: ${recoveredAddr}`);

  // Verify signer matches claimed voter
  const resolvedSigner = await resolveConsolidation(recoveredAddr.toLowerCase());
  const resolvedVoter = await resolveConsolidation(data.voter.toLowerCase());

  if (resolvedSigner.toLowerCase() !== resolvedVoter.toLowerCase()) {
    throw new Error(`Signer mismatch: ${resolvedSigner} !== ${resolvedVoter}`);
  }

  // Check proposal exists
  const proposalPath = path.join('data', 'proposals', `${data.proposalId}.json`);
  if (!fs.existsSync(proposalPath)) {
    throw new Error(`Proposal not found: ${data.proposalId}`);
  }

  const proposal = JSON.parse(fs.readFileSync(proposalPath, 'utf8'));
  if (proposal.status !== 'active') {
    throw new Error(`Proposal is not active: ${proposal.status}`);
  }

  // Check not expired
  if (new Date(proposal.expiresAt) < new Date()) {
    throw new Error('Proposal has expired');
  }

  // Check double vote
  const primaryAddr = resolvedSigner.toLowerCase();
  const votePath = path.join('data', 'votes', data.proposalId, `${primaryAddr}.json`);

  if (fs.existsSync(votePath)) {
    throw new Error(`Already voted: ${primaryAddr}`);
  }

  // Get current TDH
  const tdh = await getTDH(recoveredAddr.toLowerCase());
  data.currentTDH = tdh;

  // Write vote
  fs.mkdirSync(path.dirname(votePath), { recursive: true });
  fs.writeFileSync(votePath, JSON.stringify(data, null, 2));
  console.log(`Written: ${votePath}`);

  return { success: true, file: votePath };
}

async function main() {
  const issueBody = process.env.ISSUE_BODY || '';
  const issueTitle = process.env.ISSUE_TITLE || '';

  // Extract JSON from markdown code block
  const jsonMatch = issueBody.match(/```json\n([\s\S]*?)\n```/);
  if (!jsonMatch) {
    console.error('No JSON found in issue body');
    process.exit(1);
  }

  const data = JSON.parse(jsonMatch[1]);

  try {
    let result;
    if (issueTitle.startsWith('[PROPOSAL]')) {
      result = await processProposal(data);
    } else if (issueTitle.startsWith('[VOTE]')) {
      result = await processVote(data);
    } else {
      throw new Error('Unknown issue type');
    }

    console.log('Success:', JSON.stringify(result));

    // Output for GitHub Actions
    const outputFile = process.env.GITHUB_OUTPUT;
    if (outputFile) {
      fs.appendFileSync(outputFile, `result=success\n`);
      fs.appendFileSync(outputFile, `file=${result.file}\n`);
    }
  } catch (err) {
    console.error('Validation failed:', err.message);
    const outputFile = process.env.GITHUB_OUTPUT;
    if (outputFile) {
      fs.appendFileSync(outputFile, `result=failed\n`);
      fs.appendFileSync(outputFile, `error=${err.message}\n`);
    }
    process.exit(1);
  }
}

main();
