import { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchAccounts, startLogin, loginStatus, mediaUrl,
  accountWhoami, logoutAccount, submitLoginSms,
  saveCredentials, getCredentials, startMpLogin, mpLoginStatus,
} from '../lib/api';
import type { AccountItem, AccountWhoami } from '../lib/api';
import { dropOutdatedWhoami, getWhoamiCache, setWhoamiCache, verifyStale } from '../lib/whoami';
import PageHeader from './ui/PageHeader';
import StatusDot from './ui/StatusDot';
import Button from './ui/Button';
import Modal from './ui/Modal';
import { Input } from './ui/Field';

type QRState = {
  platform: string;
  name: string;
  state: string;       // starting | qr_ready | window_login | verifying | success | expired | error | unknown
  message: string;
  qr: string;          // outputs 相对路径
  qrTs?: number;       // 二维码文件 mtime，作 img 缓存键：码刷新一次就变，避免看到过期旧码
};

const STATE_LABEL: Record<string, string> = {
  starting: '启动中…',
  qr_ready: '请扫码',
  window_login: '窗口登录中',   // 具体怎么做由 runner 的 message 说（避免标题和消息说两遍同一句）
  scanned: '扫码成功',
  sms_required: '需短信验证',
  verifying: '验证中…',
  success: '登录成功',
  expired: '二维码已过期',
  error: '登录出错',
  unknown: '等待中…',
};

/** 头像：有 URL 就显示图（加载失败退回首字），否则显示昵称/平台名首字。 */
function Avatar({ url, name }: { url?: string; name: string }) {
  const [broken, setBroken] = useState(false);
  const initial = (name || '?').trim().charAt(0);
  if (url && !broken) {
    return <img className="account-avatar" src={url} alt={name}
      referrerPolicy="no-referrer" onError={() => setBroken(true)} />;
  }
  return <div className="account-avatar account-avatar-fallback">{initial}</div>;
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [err, setErr] = useState('');
  const [qr, setQr] = useState<QRState | null>(null);
  const [qrNonce, setQrNonce] = useState(0);   // 每次登录 +1，稳定缓存 key，避免每次轮询 img 闪烁
  const [terminalMsg, setTerminalMsg] = useState('');
  const [busy, setBusy] = useState('');
  const [logoutBusy, setLogoutBusy] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [smsBusy, setSmsBusy] = useState(false);
  const [smsErr, setSmsErr] = useState('');
  // whoami 结果缓存到 localStorage：打开页面秒显示昵称/头像，不必每次都起浏览器校验
  const [whoami, setWhoami] = useState<Record<string, AccountWhoami | 'loading'>>(() => getWhoamiCache());
  // 凭证式登录（微信公众号 AppID/AppSecret）
  const [cred, setCred] = useState<{ platform: string; name: string } | null>(null);
  const [credForm, setCredForm] = useState({ appId: '', appSecret: '', author: '' });
  const [credBusy, setCredBusy] = useState(false);
  const [credMsg, setCredMsg] = useState('');
  const [credErr, setCredErr] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const aliveRef = useRef(true);
  const qrPlatformRef = useRef('');   // 当前登录中的平台，供 submitSms 稳定引用

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; };
  }, []);

  // 真校验某平台登录态 + 拉昵称/头像（后端起浏览器，数秒）；手动「校验账号」或登录成功后调
  const runWhoami = useCallback((platform: string) => {
    setWhoami((w) => ({ ...w, [platform]: 'loading' }));
    accountWhoami(platform)
      .then((r) => { if (aliveRef.current) { setWhoami((w) => ({ ...w, [platform]: r })); setWhoamiCache(platform, r); } })
      .catch(() => {
        if (aliveRef.current) setWhoami((w) => { const n = { ...w }; delete n[platform]; return n; });
      });
  }, []);

  // 打开页面：拉「快」状态（读 status.json，不起浏览器），随后后台自愈——对缓存缺失/过期的
  // 浏览器平台逐个真校验（whoami），结果到了刷新 UI，并令陈旧的假阴性缓存被真值覆盖。
  const load = useCallback(() => {
    setErr('');
    fetchAccounts()
      .then((list) => {
        if (!aliveRef.current) return;
        setAccounts(list);
        // 登录标记变过（如 CLI 直跑 login）→ 缓存的 whoami 结论作废：卡片先回落到后端 last-known
        // （effLoggedIn 用 a.loggedIn），下面 verifyStale 把它们当缓存缺失重新真校验。
        const dropped = dropOutdatedWhoami(Object.fromEntries(list.map((a) => [a.platform, a.loginTs ?? null])));
        if (dropped.length) {
          setWhoami((w) => {
            const n = { ...w };
            for (const p of dropped) if (n[p] !== 'loading') delete n[p];
            return n;
          });
        }
        const targets = list
          .filter((a) => a.supported && a.backend !== 'biliup')
          .map((a) => a.platform);
        verifyStale(targets, {
          alive: () => aliveRef.current,
          onUpdate: (platform, r) => setWhoami((w) => ({ ...w, [platform]: r })),
        });
      })
      .catch(() => setErr('加载账号状态失败'));
  }, []);

  useEffect(() => { load(); }, [load]);

  // 切回本标签页 / 窗口重新获得焦点时自动重拉账号态——登录/退出后即使漏了一次刷新，切回来也是最新的，
  // 用户无需手动刷新页面。（登录中弹着二维码时不打扰，避免打断轮询。）
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible' && !pollRef.current) load(); };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [load]);

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const closeQr = useCallback(() => {
    stopPoll();
    setQr(null);
    setSmsCode(''); setSmsErr(''); setSmsBusy(false);
    load();
  }, [stopPoll, load]);

  const submitSms = useCallback(async () => {
    const code = smsCode.replace(/\D/g, '');
    if (code.length < 4) { setSmsErr('请输入手机收到的验证码'); return; }
    setSmsBusy(true); setSmsErr('');
    try {
      await submitLoginSms(qrPlatformRef.current, code);
      setSmsCode('');
      // 乐观切到「验证中」转圈：后端读走码→verifying；成功→success，失败→退回 sms_required 带错误
      setQr((prev) => prev && ({ ...prev, state: 'verifying', message: '正在验证验证码…' }));
      // 不停轮询：runner 读走验证码填码提交后，state 会转 success / 或退回 sms_required 重试
    } catch (e) {
      setSmsErr(e instanceof Error ? e.message : '提交验证码失败');
    } finally {
      setSmsBusy(false);
    }
  }, [smsCode]);

  // 凭证式（公众号）：打开 AppID/AppSecret 表单
  const openCred = useCallback((a: AccountItem) => {
    setCred({ platform: a.platform, name: a.name });
    setCredForm({ appId: '', appSecret: '', author: '' });
    setCredMsg(''); setCredErr('');
    getCredentials(a.platform)
      .then((c) => { if (aliveRef.current && c.configured) setCredMsg(`已配置：AppID ${c.appIdMasked}`); })
      .catch(() => { /* 未配置，忽略 */ });
  }, []);

  const closeCred = useCallback(() => { setCred(null); setCredBusy(false); load(); }, [load]);

  const submitCred = useCallback(async () => {
    if (!cred) return;
    const appId = credForm.appId.trim();
    const appSecret = credForm.appSecret.trim();
    if (!appId || !appSecret) { setCredErr('AppID 和 AppSecret 都要填'); return; }
    setCredBusy(true); setCredErr(''); setCredMsg('');
    try {
      const r = await saveCredentials(cred.platform, { appId, appSecret, name: cred.name, author: credForm.author.trim() });
      if (r.ok) {
        runWhoami(cred.platform);
        closeCred();
      } else {
        setCredErr(r.message || '验证未通过');
      }
    } catch (e) {
      setCredErr(e instanceof Error ? e.message : '保存失败');
    } finally {
      setCredBusy(false);
    }
  }, [cred, credForm, runWhoami, closeCred]);

  const handleLogin = useCallback(async (a: AccountItem) => {
    if (!a.supported) return;
    if (a.backend === 'wechat-oa') { openCred(a); return; }   // 公众号走凭证表单，不扫码
    setTerminalMsg('');
    setBusy(a.platform);
    setSmsCode(''); setSmsErr('');
    qrPlatformRef.current = a.platform;
    setQrNonce((n) => n + 1);
    try {
      const res = await startLogin(a.platform);
      if (res.mode === 'terminal') {
        setTerminalMsg(res.message || '请在终端登录');
        return;
      }
      if (res.mode === 'credentials') { openCred(a); return; }
      setQr({ platform: a.platform, name: a.name, state: res.state || 'starting',
              message: res.message || '', qr: res.qr || '' });   // qrTs 由随后的轮询填入
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const s = await loginStatus(a.platform);
          setQr((prev) => prev && ({ ...prev, state: s.state, message: s.message, qr: s.qr, qrTs: s.qrTs }));
          if (['success', 'expired', 'error'].includes(s.state)) {
            stopPoll();
            if (s.state === 'success') runWhoami(a.platform);   // 登录成功即拉账号信息
          }
        } catch { /* 忽略单次轮询失败 */ }
      }, 2000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '启动登录失败');
    } finally {
      setBusy('');
    }
  }, [stopPoll, runWhoami]);

  // 公众号后台扫码登录（数据中心取数用，独立于 AppID 凭证）
  const handleMpLogin = useCallback(async (a: AccountItem) => {
    setBusy(a.platform + ':mp');
    setSmsCode(''); setSmsErr('');
    setQrNonce((n) => n + 1);
    try {
      const res = await startMpLogin(a.platform);
      setQr({ platform: a.platform, name: a.name + ' · 后台取数', state: res.state || 'starting',
              message: res.message || '', qr: res.qr || '', qrTs: res.qrTs });
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const s = await mpLoginStatus(a.platform);
          setQr((prev) => prev && ({ ...prev, state: s.state, message: s.message, qr: s.qr, qrTs: s.qrTs }));
          if (['success', 'expired', 'error'].includes(s.state)) {
            stopPoll();
            if (s.state === 'success') {
              // 像快手一样“内存态立即翻”：wechat-oa 的 effLoggedIn 只看 a.loggedIn，这里直接把它乐观置 true，
              // 卡片瞬间变「已登录」，不必等 load() 那趟网络往返（后面 load() 再对账兜底）。
              setAccounts((list) => list.map((x) => x.platform === a.platform ? { ...x, loggedIn: true } : x));
              setWhoami((w) => { const n = { ...w }; delete n[a.platform]; return n; });
              setWhoamiCache(a.platform, null);
              runWhoami(a.platform);
              load();
            }
          }
        } catch { /* 忽略单次轮询失败 */ }
      }, 2000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '启动后台登录失败');
    } finally {
      setBusy('');
    }
  }, [stopPoll, runWhoami, load]);

  const handleLogout = useCallback(async (a: AccountItem) => {
    if (!window.confirm(`确定退出「${a.name}」的登录？登录态将被清除，下次发布需重新扫码。`)) return;
    setLogoutBusy(a.platform);
    try {
      await logoutAccount(a.platform);
      // 内存态立即翻未登录（同登录路径），不等 load() 回来
      setAccounts((list) => list.map((x) => x.platform === a.platform ? { ...x, loggedIn: false } : x));
      setWhoami((w) => { const n = { ...w }; delete n[a.platform]; return n; });
      setWhoamiCache(a.platform, null);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '退出登录失败');
    } finally {
      setLogoutBusy('');
    }
  }, [load]);

  // 卡片真实登录态：whoami 权威（已返回则以它为准，自愈假阳性），否则用后端 last-known。
  // 公众号(wechat-oa)例外：后端查 mp 会话即真值(快且权威)，直接用它，避免浏览器里过期的 whoami 缓存把已登录盖成未登录。
  const effLoggedIn = (a: AccountItem): boolean => {
    if (a.backend === 'wechat-oa') return a.loggedIn;
    const w = whoami[a.platform];
    if (w && w !== 'loading') return w.loggedIn;
    return a.loggedIn;
  };

  const status = (a: AccountItem) => {
    if (!a.supported) return <StatusDot tone="idle">待重写</StatusDot>;
    if (whoami[a.platform] === 'loading') return <StatusDot tone="idle">校验中…</StatusDot>;
    if (effLoggedIn(a)) return <StatusDot tone="ok">已登录</StatusDot>;
    return <StatusDot tone="idle">未登录</StatusDot>;
  };

  const busyFor = (a: AccountItem) => busy === a.platform || busy === a.platform + ':mp';

  return (
    <div className="page-scroll accounts-page">
      <PageHeader
        layer="publish"
        title="账号"
        description="用手机 App 扫码登录。登录状态保存在本机，之后发布不用再登。"
        actions={<Button size="sm" onClick={load}>刷新状态</Button>}
      />

      {err && <p className="accounts-error" role="alert">{err}</p>}
      {terminalMsg && <div className="accounts-notice">{terminalMsg}</div>}

      <div className="accounts-list">
        {accounts.map((a) => {
          const w = whoami[a.platform];
          const info = w && w !== 'loading' ? w : null;
          const logged = effLoggedIn(a);
          return (
            <div key={a.platform} className={`account-row${a.supported ? '' : ' is-unsupported'}`}>
              <span className="account-platform">{a.name}</span>
              <span className="account-who">
                {logged && info ? (
                  <>
                    <Avatar url={info.avatar} name={info.name || a.name} />
                    <span className="account-nick" title={info.name || ''}>{info.name || '已登录'}</span>
                  </>
                ) : (
                  // 已登录但还没有 whoami 结果（B站 不自动校验、其他平台校验中）也要占住这一栏，不能留空
                  <span className="account-note">{logged ? '已登录' : (a.note || '未登录')}</span>
                )}
              </span>
              {status(a)}
              <span className="account-actions">
                {logged ? (
                  <>
                    <Button size="sm" disabled={busyFor(a) || w === 'loading'} onClick={() => runWhoami(a.platform)}>
                      {w === 'loading' ? '校验中…' : '校验'}
                    </Button>
                    <Button size="sm" disabled={logoutBusy === a.platform} onClick={() => handleLogout(a)}>
                      {logoutBusy === a.platform ? '退出中…' : '退出'}
                    </Button>
                  </>
                ) : (
                  // 公众号与其它平台统一：都走扫码登录（公众号扫的是后台会话，用于发布+数据）
                  <Button size="sm" variant={a.supported ? 'primary' : 'secondary'}
                    disabled={!a.supported || busyFor(a)}
                    onClick={() => (a.backend === 'wechat-oa' ? handleMpLogin(a) : handleLogin(a))}>
                    {busyFor(a) ? '启动中…' : '扫码登录'}
                  </Button>
                )}
              </span>
            </div>
          );
        })}
      </div>

      <p className="accounts-warn">
        机房或代理 IP 可能被平台判为风险，二维码会弹不出来。遇到这种情况，换干净的家宽网络，或者在能正常登录的机器上登好，再把登录目录拷过来。
      </p>

      {qr && (
        <Modal title={`登录${qr.name}`} width={380} onClose={closeQr}
          footer={<Button onClick={closeQr}>{qr.state === 'success' ? '完成' : '关闭'}</Button>}>
          <p className={`qr-state${qr.state === 'success' ? ' is-ok' : ['error', 'expired'].includes(qr.state) ? ' is-bad' : ''}`}>
            {STATE_LABEL[qr.state] || qr.state}{qr.message ? `：${qr.message}` : ''}
          </p>
          {qr.state === 'sms_required' ? (
            <div>
              <p className={/错误|过期|失败|重新|未找到|未完成|不正确|失效/.test(qr.message || '') ? 'qr-error' : 'modal-text'}>
                {qr.message || '平台风控要求短信验证，验证码已发到你手机，请输入：'}
              </p>
              <Input
                className="sms-input"
                value={smsCode}
                onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                onKeyDown={(e) => { if (e.key === 'Enter') submitSms(); }}
                placeholder="短信验证码" inputMode="numeric" autoFocus />
              {smsErr && <p className="qr-error">{smsErr}</p>}
              <Button variant="primary" block loading={smsBusy} onClick={submitSms}>提交验证码</Button>
            </div>
          ) : qr.state === 'qr_ready' && qr.qr ? (
            <img className="qr-img" src={`${mediaUrl(qr.qr)}?v=${qr.qrTs || qrNonce}`} alt="登录二维码" />
          ) : qr.state === 'window_login' ? (
            // 平台拦了无头浏览器，runner 在本机弹了窗口：非终态，继续轮询；窗口里出了码也在这里给一份
            qr.qr ? (
              <img className="qr-img" src={`${mediaUrl(qr.qr)}?v=${qr.qrTs || qrNonce}`} alt="登录二维码" />
            ) : (
              <div className="loading"><div className="spinner" />
                {qr.message || '已弹出浏览器窗口，请在窗口里完成登录，不要关掉它'}</div>
            )
          ) : qr.state === 'scanned' ? (
            <div className="loading"><div className="spinner" />扫码成功，正在跳转验证…（首次可能要十几秒）</div>
          ) : qr.state === 'verifying' ? (
            // verifying 有两种：短信验证码提交中 / 登录后正在确认登录态已保存 —— 以 runner 的 message 为准
            <div className="loading"><div className="spinner" />{qr.message || '验证中…'}</div>
          ) : qr.state === 'success' ? (
            <div className="qr-done">登录成功</div>
          ) : ['error', 'expired'].includes(qr.state) ? (
            <p className="qr-error">{qr.message || '登录失败'}。可以关闭后重试，或换干净的网络。</p>
          ) : (
            <div className="loading"><div className="spinner" />准备二维码…</div>
          )}
        </Modal>
      )}

      {cred && (
        <Modal title={`配置${cred.name}`} width={440} onClose={closeCred}
          footer={(
            <>
              <Button onClick={closeCred}>关闭</Button>
              <Button variant="primary" loading={credBusy} onClick={submitCred}>保存并验证</Button>
            </>
          )}>
          <p className="modal-text">
            公众号用官方接口发布，需要填开发者凭证（公众平台 → 设置与开发 → 开发接口管理）。
            还要把本服务器的出口 IP 加进公众号的 IP 白名单，否则会报 40164。文章会发到草稿箱，群发请到公众号后台确认。
          </p>
          {credMsg && <p className="cred-ok">{credMsg}</p>}
          <label className="cred-label">AppID
            <Input value={credForm.appId} autoFocus placeholder="wx..."
              onChange={(e) => setCredForm((f) => ({ ...f, appId: e.target.value.trim() }))} />
          </label>
          <label className="cred-label">AppSecret
            <Input type="password" value={credForm.appSecret} placeholder="开发者密钥（不会回显）"
              onChange={(e) => setCredForm((f) => ({ ...f, appSecret: e.target.value.trim() }))} />
          </label>
          <label className="cred-label">默认作者（可选）
            <Input value={credForm.author} placeholder="文章署名"
              onChange={(e) => setCredForm((f) => ({ ...f, author: e.target.value }))} />
          </label>
          {credErr && <p className="qr-error">{credErr}</p>}
        </Modal>
      )}
    </div>
  );
}
