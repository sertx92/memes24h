// MEMES 24H Governance - Main Application Controller
// Hash-based routing SPA

import { CONFIG, GITHUB_RAW } from './config.js';
import { connectWallet, disconnectWallet, getAddress, isConnected } from './wallet.js';
import { resolveIdentity, formatTDH, shortAddress, verifyWave } from './api6529.js';
import { listProposals, getProposal, getProposalVotes, tallyVotes, createProposal, hasVoted } from './proposals.js';
import { submitVote } from './voting.js';

// State
let userIdentity = null;
let currentView = 'dashboard';

// DOM
const app = document.getElementById('app');
const userArea = document.getElementById('userArea');

// === ROUTING ===
function route() {
  const hash = window.location.hash || '#/';
  if (hash === '#/' || hash === '#') renderDashboard();
  else if (hash.startsWith('#/proposal/')) renderProposalDetail(hash.split('#/proposal/')[1]);
  else if (hash === '#/create') renderCreateProposal();
  else if (hash === '#/config') renderConfig();
  else renderDashboard();
}

window.addEventListener('hashchange', route);

// === WALLET CONNECTION ===
window.connectWalletBtn = async function() {
  try {
    const address = await connectWallet();
    userIdentity = await resolveIdentity(address);
    renderUserArea();
    route(); // refresh current view
  } catch (err) {
    showToast(err.message, 'error');
  }
};

window.disconnectWalletBtn = function() {
  disconnectWallet();
  userIdentity = null;
  renderUserArea();
  route();
};

window.addEventListener('wallet-changed', async (e) => {
  if (e.detail.address) {
    userIdentity = await resolveIdentity(e.detail.address);
  } else {
    userIdentity = null;
  }
  renderUserArea();
  route();
});

// === USER AREA ===
function renderUserArea() {
  if (!userIdentity) {
    userArea.innerHTML = `
      <button class="btn btn-connect" onclick="connectWalletBtn()">Connect Wallet</button>
    `;
    return;
  }

  const delegateTag = userIdentity.isDelegate ? '<span class="tag-delegate">via delegate</span>' : '';
  const pfpSrc = userIdentity.pfp
    ? (userIdentity.pfp.startsWith('ipfs://') ? userIdentity.pfp.replace('ipfs://', 'https://ipfs.io/ipfs/') : userIdentity.pfp)
    : '';
  const pfpHtml = pfpSrc ? `<img src="${pfpSrc}" class="user-pfp" alt="">` : '<div class="user-pfp-placeholder"></div>';

  userArea.innerHTML = `
    <div class="user-info">
      ${pfpHtml}
      <div class="user-details">
        <div class="user-handle">${userIdentity.handle || shortAddress(userIdentity.address)} ${delegateTag}</div>
        <div class="user-tdh">${formatTDH(userIdentity.tdh)} TDH &middot; Level ${userIdentity.level}</div>
      </div>
      <button class="btn btn-sm btn-disconnect" onclick="disconnectWalletBtn()">Disconnect</button>
    </div>
  `;
}

// === DASHBOARD ===
async function renderDashboard() {
  currentView = 'dashboard';
  app.innerHTML = '<div class="loading">Loading proposals...</div>';

  const proposals = await listProposals();
  const configRes = await fetch(`${GITHUB_RAW}/${CONFIG.WAVES_CONFIG_PATH}?t=${Date.now()}`);
  const config = await configRes.json();

  const activeProposals = proposals.filter(p => p.status === 'active');
  const pastProposals = proposals.filter(p => p.status !== 'active');

  let html = `
    <div class="section-header">
      <h2>Active Proposals</h2>
      ${userIdentity && userIdentity.tdh >= CONFIG.MIN_TDH_PROPOSE
        ? '<a href="#/create" class="btn btn-primary">+ New Proposal</a>'
        : ''}
    </div>
  `;

  if (activeProposals.length === 0) {
    html += '<div class="empty-state">No active proposals. ';
    if (userIdentity && userIdentity.tdh >= CONFIG.MIN_TDH_PROPOSE) {
      html += '<a href="#/create">Create one</a>';
    } else {
      html += `Need ${formatTDH(CONFIG.MIN_TDH_PROPOSE)} TDH to propose.`;
    }
    html += '</div>';
  } else {
    html += '<div class="proposals-grid">';
    for (const p of activeProposals) {
      html += renderProposalCard(p);
    }
    html += '</div>';
  }

  // Current config
  html += `
    <div class="section-header" style="margin-top:32px">
      <h2>Current News Sources</h2>
      <a href="#/config" class="btn btn-sm">View Config</a>
    </div>
    <div class="config-grid">
      ${config.waves.map(w => `
        <div class="config-item">
          <span class="config-type">${w.type}</span>
          <span class="config-name">${w.name}</span>
        </div>
      `).join('')}
      ${config.collections.map(c => `
        <div class="config-item">
          <span class="config-type">market</span>
          <span class="config-name">${c.name}</span>
        </div>
      `).join('')}
    </div>
  `;

  // Past proposals
  if (pastProposals.length > 0) {
    html += `<div class="section-header" style="margin-top:32px"><h2>Past Proposals</h2></div>`;
    html += '<div class="proposals-grid">';
    for (const p of pastProposals) {
      html += renderProposalCard(p);
    }
    html += '</div>';
  }

  app.innerHTML = html;
}

function renderProposalCard(p) {
  const isExpired = new Date(p.expiresAt) < new Date();
  const statusClass = p.status === 'active' ? (isExpired ? 'status-expired' : 'status-active') : (p.status === 'passed' ? 'status-passed' : 'status-failed');
  const statusLabel = p.status === 'active' ? (isExpired ? 'EXPIRED' : 'ACTIVE') : p.status.toUpperCase();
  const daysLeft = Math.max(0, Math.ceil((new Date(p.expiresAt) - new Date()) / 86400000));
  const actionLabel = p.action === 'add' ? 'Add' : 'Remove';

  return `
    <a href="#/proposal/${p.id}" class="proposal-card">
      <div class="proposal-header">
        <span class="proposal-action action-${p.action}">${actionLabel}</span>
        <span class="proposal-status ${statusClass}">${statusLabel}</span>
      </div>
      <div class="proposal-wave">${p.waveName}</div>
      <div class="proposal-reason">${p.reason || ''}</div>
      <div class="proposal-meta">
        <span>by ${p.proposer.handle || shortAddress(p.proposer.address)}</span>
        <span>${p.status === 'active' && !isExpired ? daysLeft + 'd left' : ''}</span>
      </div>
    </a>
  `;
}

// === PROPOSAL DETAIL ===
async function renderProposalDetail(id) {
  currentView = 'proposal';
  app.innerHTML = '<div class="loading">Loading proposal...</div>';

  const proposal = await getProposal(id);
  if (!proposal) {
    app.innerHTML = '<div class="empty-state">Proposal not found. <a href="#/">Back</a></div>';
    return;
  }

  const votes = await getProposalVotes(id);
  const tally = await tallyVotes(votes);
  const isExpired = new Date(proposal.expiresAt) < new Date();
  const daysLeft = Math.max(0, Math.ceil((new Date(proposal.expiresAt) - new Date()) / 86400000));
  const voted = userIdentity ? await hasVoted(id) : false;

  const actionLabel = proposal.action === 'add' ? 'Add Wave' : 'Remove Wave';

  let voteButtons = '';
  if (userIdentity && proposal.status === 'active' && !isExpired && !voted) {
    voteButtons = `
      <div class="vote-actions">
        <button class="btn btn-yes" id="btnYes">Vote YES (${formatTDH(userIdentity.tdh)} TDH)</button>
        <button class="btn btn-no" id="btnNo">Vote NO (${formatTDH(userIdentity.tdh)} TDH)</button>
      </div>
    `;
  } else if (voted) {
    voteButtons = '<div class="voted-msg">You have already voted on this proposal.</div>';
  } else if (!userIdentity) {
    voteButtons = '<div class="voted-msg">Connect your wallet to vote.</div>';
  }

  app.innerHTML = `
    <a href="#/" class="back-link">&larr; Back to Dashboard</a>
    <div class="proposal-detail">
      <div class="proposal-detail-header">
        <span class="proposal-action action-${proposal.action}">${actionLabel}</span>
        <h2>${proposal.waveName}</h2>
      </div>

      <div class="proposal-info-grid">
        <div class="info-box">
          <div class="info-label">Proposer</div>
          <div class="info-value">${proposal.proposer.handle || shortAddress(proposal.proposer.address)}</div>
          <div class="info-sub">${formatTDH(proposal.proposer.tdh)} TDH</div>
        </div>
        <div class="info-box">
          <div class="info-label">Time Left</div>
          <div class="info-value">${isExpired ? 'Expired' : daysLeft + ' days'}</div>
          <div class="info-sub">${new Date(proposal.expiresAt).toLocaleDateString()}</div>
        </div>
        <div class="info-box">
          <div class="info-label">Status</div>
          <div class="info-value">${proposal.status.toUpperCase()}</div>
          <div class="info-sub">${tally.yesCount + tally.noCount} votes</div>
        </div>
      </div>

      <div class="reason-box">
        <div class="info-label">Reason</div>
        <p>${proposal.reason || 'No reason provided.'}</p>
      </div>

      <div class="tally-section">
        <div class="tally-header">
          <span>Progress: ${formatTDH(tally.yesTDH)} / ${formatTDH(CONFIG.TDH_THRESHOLD_PASS)} TDH</span>
          <span>${tally.progress.toFixed(1)}%</span>
        </div>
        <div class="tally-bar">
          <div class="tally-fill" style="width: ${tally.progress}%"></div>
        </div>
        <div class="tally-detail">
          <span class="tally-yes">YES: ${formatTDH(tally.yesTDH)} TDH (${tally.yesCount} votes)</span>
          <span class="tally-no">NO: ${formatTDH(tally.noTDH)} TDH (${tally.noCount} votes)</span>
        </div>
      </div>

      ${voteButtons}

      ${tally.votes.length > 0 ? `
        <div class="votes-list">
          <h3>Votes</h3>
          ${tally.votes.map(v => `
            <div class="vote-item">
              <span class="vote-badge vote-${v.vote}">${v.vote.toUpperCase()}</span>
              <span class="vote-handle">${v.voterHandle || shortAddress(v.voter)}</span>
              <span class="vote-tdh">${formatTDH(v.currentTDH)} TDH</span>
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>
  `;

  // Attach vote handlers
  const btnYes = document.getElementById('btnYes');
  const btnNo = document.getElementById('btnNo');
  if (btnYes) btnYes.addEventListener('click', () => handleVote(id, 'yes'));
  if (btnNo) btnNo.addEventListener('click', () => handleVote(id, 'no'));
}

async function handleVote(proposalId, vote) {
  try {
    await submitVote(proposalId, vote);
    showToast('Vote submitted! It will be processed by GitHub Actions.', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// === CREATE PROPOSAL ===
async function renderCreateProposal() {
  currentView = 'create';

  if (!userIdentity) {
    app.innerHTML = '<div class="empty-state">Connect your wallet to create a proposal. <a href="#/">Back</a></div>';
    return;
  }

  if (userIdentity.tdh < CONFIG.MIN_TDH_PROPOSE) {
    app.innerHTML = `<div class="empty-state">You need ${formatTDH(CONFIG.MIN_TDH_PROPOSE)} TDH to create a proposal. You have ${formatTDH(userIdentity.tdh)}. <a href="#/">Back</a></div>`;
    return;
  }

  app.innerHTML = `
    <a href="#/" class="back-link">&larr; Back to Dashboard</a>
    <div class="create-form">
      <h2>Create Proposal</h2>
      <p class="form-sub">Propose adding or removing a wave from the MEMES 24H news sources.</p>

      <div class="form-group">
        <label>Action</label>
        <select id="propAction">
          <option value="add">Add Wave</option>
          <option value="remove">Remove Wave</option>
        </select>
      </div>

      <div class="form-group">
        <label>Wave ID (UUID from 6529.io URL)</label>
        <input type="text" id="propWaveId" placeholder="e.g. b38288e6-ca9d-45ce-8323-3dc5e094f04e">
        <div class="form-hint">Copy the wave UUID from the 6529.io URL</div>
        <div id="waveVerify" class="wave-verify"></div>
      </div>

      <div class="form-group">
        <label>Reason</label>
        <textarea id="propReason" rows="3" placeholder="Why should this wave be added/removed?"></textarea>
      </div>

      <div class="form-footer">
        <span class="form-cost">Your TDH: ${formatTDH(userIdentity.tdh)}</span>
        <button class="btn btn-primary" id="btnSubmitProposal">Sign & Submit Proposal</button>
      </div>
    </div>
  `;

  // Verify wave on blur
  document.getElementById('propWaveId').addEventListener('blur', async (e) => {
    const waveId = e.target.value.trim();
    const verifyEl = document.getElementById('waveVerify');
    if (!waveId) { verifyEl.innerHTML = ''; return; }

    verifyEl.innerHTML = '<span class="verifying">Verifying...</span>';
    const wave = await verifyWave(waveId);
    if (wave.exists) {
      verifyEl.innerHTML = `<span class="verified">Found: ${wave.name}</span>`;
    } else {
      verifyEl.innerHTML = '<span class="not-found">Wave not found on 6529.io</span>';
    }
  });

  // Submit handler
  document.getElementById('btnSubmitProposal').addEventListener('click', async () => {
    const action = document.getElementById('propAction').value;
    const waveId = document.getElementById('propWaveId').value.trim();
    const reason = document.getElementById('propReason').value.trim();

    if (!waveId) { showToast('Enter a wave ID', 'error'); return; }
    if (!reason) { showToast('Enter a reason', 'error'); return; }

    try {
      await createProposal(action, waveId, reason);
      showToast('Proposal submitted! It will be processed shortly.', 'success');
      window.location.hash = '#/';
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

// === CONFIG VIEW ===
async function renderConfig() {
  app.innerHTML = '<div class="loading">Loading config...</div>';

  const res = await fetch(`${GITHUB_RAW}/${CONFIG.WAVES_CONFIG_PATH}?t=${Date.now()}`);
  const config = await res.json();

  app.innerHTML = `
    <a href="#/" class="back-link">&larr; Back to Dashboard</a>
    <h2>Current News Configuration</h2>
    <p class="form-sub">This is what the MEMES 24H news card currently monitors. Create a proposal to change it.</p>

    <h3 style="margin-top:24px">Waves</h3>
    <div class="config-detail-grid">
      ${config.waves.map(w => `
        <div class="config-detail-item">
          <div class="config-detail-name">${w.name}</div>
          <div class="config-detail-meta">
            <span class="config-type">${w.type}</span>
            <span>Added by ${w.addedBy}</span>
            <span>${new Date(w.addedAt).toLocaleDateString()}</span>
          </div>
          <div class="config-detail-id">${w.id}</div>
        </div>
      `).join('')}
    </div>

    <h3 style="margin-top:24px">Collections (OpenSea)</h3>
    <div class="config-detail-grid">
      ${config.collections.map(c => `
        <div class="config-detail-item">
          <div class="config-detail-name">${c.name}</div>
          <div class="config-detail-meta">
            <span class="config-type">market</span>
            <span>Added by ${c.addedBy}</span>
          </div>
          <div class="config-detail-id">${c.slug}</div>
        </div>
      `).join('')}
    </div>
  `;
}

// === TOAST ===
function showToast(message, type = 'info') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

// === INIT ===
renderUserArea();
route();
