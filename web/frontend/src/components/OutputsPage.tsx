import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { fetchOutputs, fetchOutputContent, mediaUrl, deleteOutput } from '../lib/api';
import type { OutputNode, OutputMeta } from '../lib/api';
import { renderMarkdown } from '../lib/sanitize';
import { IconImage, IconVideo, IconMusic, IconFile, IconFolder, IconRefresh, IconChevron, IconTrash } from './icons';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Tag from './ui/Tag';
import type { TagTone } from './ui/Tag';
import Tabs from './ui/Tabs';
import EmptyState from './ui/EmptyState';

const FILTERS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'image', label: '图片' },
  { key: 'video', label: '视频' },
  { key: 'audio', label: '音频' },
  { key: 'text', label: '文档' },
];

const KIND_LABEL: Record<string, string> = {
  article: '文章', 'xhs-note': '小红书', video: '视频', cards: '卡片',
  poster: '海报', audio: '音频', other: '其他',
};
const STATUS_LABEL: Record<string, string> = { draft: '草稿', ready: '待发', published: '已发' };
const STATUS_TONE: Record<string, TagTone> = { draft: 'neutral', ready: 'warn', published: 'ok' };

function kindIcon(kind: string | undefined, size = 30) {
  if (kind === 'video') return <IconVideo size={size} />;
  if (kind === 'audio') return <IconMusic size={size} />;
  if (kind === 'image') return <IconImage size={size} />;
  return <IconFile size={size} />;
}
const isHtml = (name: string) => /\.html?$/i.test(name);
const kindLabel = (f: OutputNode) =>
  f.kind === 'text' ? (isHtml(f.name) ? '卡片' : '文档')
    : f.kind === 'image' ? '图片' : f.kind === 'video' ? '视频' : f.kind === 'audio' ? '音频' : '文件';

/** 递归找目录下第一张图/视频作封面缩略图。 */
function firstMedia(node: OutputNode): OutputNode | null {
  if (node.type === 'file') return (node.kind === 'image' || node.kind === 'video') ? node : null;
  for (const c of node.children || []) {
    const m = firstMedia(c);
    if (m) return m;
  }
  return null;
}

/** 展示头声明的封面 → 伪 file 节点（供 Thumb 渲染）。 */
function coverNode(m?: OutputMeta): OutputNode | null {
  if (!m?.cover) return null;
  const kind = /\.(mp4|mov|webm|mkv)$/i.test(m.cover) ? 'video' : 'image';
  return { name: 'cover', type: 'file', path: m.cover, kind } as OutputNode;
}

/** 按名称路径解析到当前目录的 children（stackNames 稳定，刷新后仍有效）。 */
function resolvePath(roots: OutputNode[], names: string[]): OutputNode[] {
  let nodes = roots;
  for (const nm of names) {
    const found = nodes.find((n) => n.type === 'dir' && n.name === nm);
    if (!found) return nodes;   // 路径失效（被删/改）→ 停在能解析到的层
    nodes = found.children || [];
  }
  return nodes;
}

function Thumb({ f, big }: { f: OutputNode | null; big?: boolean }) {
  if (f && f.kind === 'image') return <img src={mediaUrl(f.path)} alt="" loading="lazy" />;
  if (f && f.kind === 'video') return <video src={mediaUrl(f.path)} preload="metadata" muted />;
  return <div className="gcard-ph">{kindIcon(f?.kind, big ? 34 : 30)}</div>;
}

interface OutputsPageProps {
  /** 从对话跳转进来的目录（outputs 相对路径，不含 outputs/ 前缀）；消费后由父层清空 */
  jumpPath?: string;
  onJumpHandled?: () => void;
}

export default function OutputsPage({ jumpPath, onJumpHandled }: OutputsPageProps) {
  const [roots, setRoots] = useState<OutputNode[]>([]);
  const [treeError, setTreeError] = useState('');
  const [stack, setStack] = useState<string[]>([]);   // 当前所在的文件夹名称路径
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState<OutputNode | null>(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const reqSeq = useRef(0);

  const load = useCallback(() => {
    setTreeError('');
    fetchOutputs().then(setRoots).catch(() => setTreeError('加载产物列表失败'));
  }, []);
  useEffect(() => { load(); }, [load]);

  // 对话里的目录路径跳转：展开到对应层级（路径失效时 resolvePath 自动停在能到的层）
  useEffect(() => {
    if (!jumpPath) return;
    setStack(jumpPath.split('/').filter(Boolean));
    setFilter('all');
    onJumpHandled?.();
  }, [jumpPath, onJumpHandled]);

  const currentNodes = useMemo(() => resolvePath(roots, stack), [roots, stack]);
  const dirs = useMemo(
    () => currentNodes.filter((n) => n.type === 'dir').sort((a, b) => (b.mtime || 0) - (a.mtime || 0)),
    [currentNodes]);
  const files = useMemo(() => {
    const fs = currentNodes.filter((n) => n.type === 'file').sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
    return filter === 'all' ? fs : fs.filter((f) => f.kind === filter);
  }, [currentNodes, filter]);

  const atTop = stack.length === 0;
  const atProjectRoot = stack.length === 1;
  // 当前项目的展示头（进入项目后才有），用于「成品/素材」分区
  const projectMeta = useMemo(
    () => (stack.length >= 1 ? roots.find((r) => r.name === stack[0])?.meta : undefined),
    [roots, stack]);
  const deliverableSet = useMemo(
    () => new Set(atProjectRoot ? (projectMeta?.deliverablePaths || []) : []),
    [projectMeta, atProjectRoot]);
  const hasSplit = atProjectRoot && deliverableSet.size > 0;
  const deliverableFiles = useMemo(
    () => (hasSplit ? files.filter((f) => deliverableSet.has(f.path)) : []),
    [files, deliverableSet, hasSplit]);
  const restFiles = useMemo(
    () => (hasSplit ? files.filter((f) => !deliverableSet.has(f.path)) : files),
    [files, deliverableSet, hasSplit]);

  const enterDir = useCallback((name: string) => { setStack((s) => [...s, name]); setFilter('all'); }, []);
  const goTo = useCallback((depth: number) => { setStack((s) => s.slice(0, depth)); setFilter('all'); }, []);

  const remove = useCallback(async (node: OutputNode) => {
    const isDir = node.type === 'dir';
    const label = isDir ? `项目/文件夹「${node.meta?.title || node.name}」及其全部内容` : `文件「${node.name}」`;
    if (!window.confirm(`确定删除${label}？\n此操作不可恢复。`)) return;
    try {
      await deleteOutput(node.path);
      setSelected((cur) => (cur?.path === node.path ? null : cur));
      load();
    } catch (err) {
      alert((err as Error).message || '删除失败');
    }
  }, [load]);

  const open = useCallback(async (f: OutputNode) => {
    const seq = ++reqSeq.current;
    setSelected(f); setContent('');
    if (f.kind === 'text' && !isHtml(f.name)) {
      setLoading(true);
      try {
        const res = await fetchOutputContent(f.path);
        if (seq === reqSeq.current) setContent(res.isBinary ? '' : res.content);
      } finally { if (seq === reqSeq.current) setLoading(false); }
    }
  }, []);

  const preview = () => {
    if (!selected) return null;
    const url = mediaUrl(selected.path);
    if (selected.kind === 'image') return <img className="outputs-media" src={url} alt={selected.name} />;
    if (selected.kind === 'video') return <video className="outputs-media" src={url} controls />;
    if (selected.kind === 'audio') return <audio className="outputs-audio" src={url} controls />;
    if (selected.kind === 'text' && isHtml(selected.name)) return (
      <>
        {/* allow-scripts：让预览页自带的「复制到公众号」按钮(execCommand('copy'))能运行；
            allow="clipboard-write"：授予剪贴板写权限。不给 allow-same-origin —— iframe 保持
            opaque origin，脚本跑得起来但访问不到本站，安全。(修复：内嵌预览里复制按钮点了没反应) */}
        <iframe className="outputs-iframe" src={`${url}?v=${selected.mtime ?? 0}`} title={selected.name} sandbox="allow-scripts" allow="clipboard-write" />
        <div className="outputs-open"><a href={url} target="_blank" rel="noreferrer">在新标签打开</a></div>
      </>
    );
    if (selected.kind === 'text') {
      if (loading) return <div className="loading"><div className="spinner" />加载中…</div>;
      return <div className="outputs-viewer-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />;
    }
    return <div className="outputs-nopreview">无法预览。<a href={url} download>下载 {selected.name}</a></div>;
  };

  /** 项目/文件夹卡片：顶层项目用展示头（标题/平台/状态/封面），嵌套子文件夹回退朴素样式。 */
  const renderDir = (d: OutputNode) => {
    const m = d.meta;
    const cover = coverNode(m) || firstMedia(d);
    return (
      <div key={d.path} className="card card-hover gcard">
        <button type="button" className="gcard-main" onClick={() => enterDir(d.name)}>
        <div className="gcard-thumb">
          <span className="gcard-kind"><Tag>{m?.kind ? (KIND_LABEL[m.kind] || m.kind) : '文件夹'}</Tag></span>
          {cover ? <Thumb f={cover} big /> : <div className="gcard-ph"><IconFolder size={38} /></div>}
        </div>
        <div className="gcard-meta">
          <div className="gcard-name" title={m?.title || d.name}>
            {!m && <IconFolder size={13} />} {m?.title || d.name}
          </div>
          <div className="gcard-sub">
            {m?.platform && <Tag>{m.platform}</Tag>}
            {m?.status && <Tag tone={STATUS_TONE[m.status] || 'neutral'}>{STATUS_LABEL[m.status] || m.status}</Tag>}
            <span>{d.fileCount ?? 0} 个文件</span>
          </div>
        </div>
        </button>
        <button type="button" className="gcard-del" title="删除" aria-label="删除" onClick={() => remove(d)}><IconTrash size={14} /></button>
      </div>
    );
  };

  const renderFile = (f: OutputNode) => (
    <div key={f.path} className="card card-hover gcard">
      <button type="button" className="gcard-main" onClick={() => open(f)}>
        <div className="gcard-thumb">
          <span className="gcard-kind"><Tag>{kindLabel(f)}</Tag></span>
          <Thumb f={f} />
        </div>
        <div className="gcard-meta">
          <div className="gcard-name" title={f.name}>{f.name}</div>
        </div>
      </button>
      <button type="button" className="gcard-del" title="删除" aria-label="删除" onClick={() => remove(f)}><IconTrash size={14} /></button>
    </div>
  );

  const empty = dirs.length === 0 && files.length === 0;

  return (
    <div className="page-scroll gallery-page">
      <PageHeader
        layer="produce"
        title={<>
          <button type="button" className="crumb" onClick={() => goTo(0)}>内容库</button>
          {stack.map((name, i) => (
            <span key={i}>
              <span className="crumb-sep">/</span>
              {i === stack.length - 1
                ? (projectMeta?.title && i === 0 ? projectMeta.title : name)
                : <button type="button" className="crumb" onClick={() => goTo(i + 1)}>{name}</button>}
            </span>
          ))}
        </>}
        description={atTop
          ? `按项目归档，共 ${roots.length} 个项目。点项目进去看成品与素材。`
          : `${dirs.length} 个文件夹 · ${files.length} 个文件（可继续点开子文件夹）`}
        actions={<Button size="sm" icon={<IconRefresh size={14} />} onClick={load}>刷新</Button>}
      />

      {treeError && <div className="notice-error">{treeError}</div>}

      {/* 项目主题标签（进入项目根时展示） */}
      {atProjectRoot && projectMeta?.tags && projectMeta.tags.length > 0 && (
        <div className="gallery-filters">
          {projectMeta.tags.map((t) => <Tag key={t}>#{t}</Tag>)}
        </div>
      )}

      {/* 面包屑返回 + 文件过滤（进入任意层后显示） */}
      {stack.length > 0 && (
        <div className="gallery-filters">
          <Button size="sm" icon={<span className="gallery-back"><IconChevron size={13} /></span>} onClick={() => goTo(stack.length - 1)}>返回上级</Button>
          {files.length > 0 && <Tabs size="sm" ariaLabel="文件类型" items={FILTERS} value={filter} onChange={setFilter} />}
        </div>
      )}

      {empty && !treeError ? (
        <EmptyState text={atTop ? '还没有产物——去对话或技能库生成第一条内容吧' : '这个文件夹是空的'} />
      ) : hasSplit ? (
        <>
          {/* 成品区 */}
          {deliverableFiles.length > 0 && (
            <>
              <div className="outputs-section">成品 · {deliverableFiles.length}</div>
              <div className="gallery-grid">{deliverableFiles.map(renderFile)}</div>
            </>
          )}
          {/* 素材 / 过程文件区 */}
          {(dirs.length > 0 || restFiles.length > 0) && (
            <>
              <div className="outputs-section outputs-section-later">素材 / 过程文件</div>
              <div className="gallery-grid">
                {dirs.map(renderDir)}
                {restFiles.map(renderFile)}
              </div>
            </>
          )}
        </>
      ) : (
        <div className="gallery-grid">
          {dirs.map(renderDir)}
          {files.map(renderFile)}
        </div>
      )}

      {selected && (
        <div className="drawer-overlay" onClick={() => setSelected(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header outputs-drawer-head">
              <div className="outputs-drawer-name">
                <h3 className="outputs-drawer-title">{selected.name}</h3>
                <div className="outputs-drawer-path">{selected.path}</div>
              </div>
              <button className="icon-btn" aria-label="关闭" onClick={() => setSelected(null)}>×</button>
            </div>
            <div className="drawer-body">{preview()}</div>
            <div className="outputs-drawer-foot">
              <Button variant="danger" size="sm" icon={<IconTrash size={13} />} onClick={() => remove(selected)}>删除此文件</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
