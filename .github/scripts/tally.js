// MEMES 24H Governance - Proposal Tally
// Runs on schedule via GitHub Actions
// Checks all active proposals, tallies votes, updates config if passed

const fs = require('fs');
const path = require('path');

const API_6529 = 'https://api.6529.io/api';
const TDH_THRESHOLD = 10_000_000;
const PROPOSALS_DIR = 'data/proposals';
const VOTES_DIR = 'data/votes';
const CONFIG_PATH = 'data/waves-config.json';

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) return null;
  return res.json();
}

async function getTDH(address) {
  try {
    const data = await fetchJSON(`${API_6529}/profiles/${address}`);
    return data?.consolidation?.tdh || 0;
  } catch {
    return 0;
  }
}

async function tallyProposal(proposal) {
  const votesDir = path.join(VOTES_DIR, proposal.id);
  if (!fs.existsSync(votesDir)) return { yesTDH: 0, noTDH: 0 };

  const voteFiles = fs.readdirSync(votesDir).filter(f => f.endsWith('.json'));
  let yesTDH = 0;
  let noTDH = 0;

  for (const file of voteFiles) {
    const vote = JSON.parse(fs.readFileSync(path.join(votesDir, file), 'utf8'));
    const address = vote.voter || vote.submittedBy || '';
    const currentTDH = await getTDH(address.toLowerCase());

    if (vote.vote === 'yes') yesTDH += currentTDH;
    else noTDH += currentTDH;
  }

  return { yesTDH, noTDH, totalVotes: voteFiles.length };
}

async function main() {
  if (!fs.existsSync(PROPOSALS_DIR)) {
    console.log('No proposals directory');
    return;
  }

  const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  let configChanged = false;

  const proposalFiles = fs.readdirSync(PROPOSALS_DIR).filter(f => f.endsWith('.json'));

  for (const file of proposalFiles) {
    const filePath = path.join(PROPOSALS_DIR, file);
    const proposal = JSON.parse(fs.readFileSync(filePath, 'utf8'));

    if (proposal.status !== 'active') continue;

    const isExpired = new Date(proposal.expiresAt) < new Date();
    const tally = await tallyProposal(proposal);

    console.log(`${proposal.id}: YES ${tally.yesTDH} / NO ${tally.noTDH} / Threshold ${TDH_THRESHOLD} / Expired: ${isExpired}`);

    if (tally.yesTDH >= TDH_THRESHOLD) {
      // PASSED
      proposal.status = 'passed';
      proposal.passedAt = new Date().toISOString();
      proposal.finalTally = tally;

      if (proposal.action === 'add') {
        // Add wave to config
        const exists = config.waves.some(w => w.id === proposal.waveId);
        if (!exists) {
          config.waves.push({
            id: proposal.waveId,
            name: proposal.waveName,
            type: 'chat',
            addedBy: proposal.proposer.handle || proposal.proposer.address,
            addedAt: new Date().toISOString(),
            proposalId: proposal.id
          });
          configChanged = true;
          console.log(`  -> Added wave: ${proposal.waveName}`);
        }
      } else if (proposal.action === 'remove') {
        // Remove wave from config
        const idx = config.waves.findIndex(w => w.id === proposal.waveId);
        if (idx !== -1) {
          config.waves.splice(idx, 1);
          configChanged = true;
          console.log(`  -> Removed wave: ${proposal.waveName}`);
        }
      }

      fs.writeFileSync(filePath, JSON.stringify(proposal, null, 2));
      console.log(`  -> Marked as PASSED`);
    } else if (isExpired) {
      // FAILED (expired without reaching threshold)
      proposal.status = 'failed';
      proposal.failedAt = new Date().toISOString();
      proposal.finalTally = tally;
      fs.writeFileSync(filePath, JSON.stringify(proposal, null, 2));
      console.log(`  -> Marked as FAILED (expired)`);
    }
  }

  if (configChanged) {
    config.lastUpdated = new Date().toISOString();
    config.version++;
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    console.log('Config updated!');
  }
}

main().catch(err => {
  console.error('Tally failed:', err);
  process.exit(1);
});
