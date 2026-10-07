/**
 * MobileUploadE — 모바일 업로드(E안): 촬영 우선 + 스캔 애니메이션 + 다중 촬영 트레이.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.06.18      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 *
 * Author: kimzion77
 * Since: 2026.06.18
 */
'use client';

/**
 * MobileUploadE — 모바일 업로드(E안): 촬영 우선 + 스캔 애니메이션 + 다중 촬영 트레이.
 *
 * 디자이너 명세 `업로드 E안`을 이식. 문서 종류별로 제목·설명·주버튼만 바뀌고
 * 색은 브랜드 네이비로 통일(형식 나열·부연 문구 미노출).
 *
 *   idle(안내) ─[촬영/파일]→ scanning(빔 애니메이션 ~1.8s) → done(촬영 트레이)
 *   done ─[+]→ scanning(장 추가) / 트레이 ×→ 해당 장 삭제(0장이면 idle)
 *
 * 실제 추출/분석은 부모의 '검토 시작하기'(startReview)에서 일괄 수행 —
 * 여기서는 파일(촬영분)만 모은다. value/onChange 로 부모가 files 를 소유.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { DocumentType } from '@/types/review';

import styles from './MobileUploadE.module.css';

const IMG_EXT = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp'];
const DOC_EXT = ['.docx', '.hwp', '.hwpx', '.pdf', '.txt'];
// 사진 촬영: capture="environment" 로 모바일에서 후면 카메라를 바로 연다
// (capture 없이 image/* 만 주면 OS 가 '카메라/앨범/파일' 선택지를 띄워 카메라 직행이 안 됨).
// 앨범·파일에서 고르는 경로는 아래 '파일에서 선택' 버튼(fileRef)이 담당.
const ACCEPT_IMAGE = ['image/*', ...IMG_EXT].join(',');
// 파일에서 선택: accept 를 주지 않아 네이티브 '파일' 브라우저가 문서·이미지
// 등 모든 파일을 보여준다(사용자 요구). 지원 형식은 선택 후 ALLOWED 로 검증.
const ALLOWED = [...DOC_EXT, ...IMG_EXT];

interface Conf {
  h: string;
  p: string;
  primary: 'cam' | 'file';
  camLabel: string;
  fileLabel: string;
}

const CONF: Record<DocumentType, Conf> = {
  'employment-contract': {
    h: '계약서를 사진으로 찍어주세요',
    p: '글자를 자동으로 읽어 위반·누락 항목을 검토합니다.',
    primary: 'cam',
    camLabel: '사진 촬영',
    fileLabel: '파일에서 선택',
  },
  'work-rules': {
    h: '취업규칙 파일을 올려주세요',
    p: '필수 기재사항과 불이익 변경 여부를 검토합니다.',
    primary: 'file',
    camLabel: '사진으로 찍기',
    fileLabel: '파일 올리기',
  },
};

function CamIcon() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden>
      <path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L19 6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <circle cx="12" cy="12.5" r="3.5" />
    </svg>
  );
}
function FileIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </svg>
  );
}
function ShieldIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V5z" />
    </svg>
  );
}

interface Props {
  docType: DocumentType;
  value: File[];
  onChange: (files: File[]) => void;
}

export default function MobileUploadE({ docType, value, onChange }: Props) {
  const conf = CONF[docType] ?? CONF['employment-contract'];
  const [phase, setPhase] = useState<'idle' | 'scanning' | 'done'>(
    value.length > 0 ? 'done' : 'idle',
  );
  const [err, setErr] = useState<string | null>(null);
  // 큰 미리보기에 띄울 현재 장 (썸네일 탭으로 전환).
  const [current, setCurrent] = useState(0);
  const camRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const scanTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (scanTimer.current) clearTimeout(scanTimer.current);
    },
    [],
  );
  // 외부에서 files 가 비워지면 idle 로 복귀 + current 범위 보정
  useEffect(() => {
    if (value.length === 0) setPhase((p) => (p === 'done' ? 'idle' : p));
    setCurrent((c) => Math.min(c, Math.max(0, value.length - 1)));
  }, [value.length]);

  const extOf = (n: string) => {
    const i = n.lastIndexOf('.');
    return i < 0 ? '' : n.slice(i).toLowerCase();
  };

  // 올린 파일 미리보기 — 이미지는 실제 썸네일, 문서는 아이콘+이름. (트레이 대신 크게)
  const previews = useMemo(
    () =>
      value.map((f) => {
        const isImg =
          f.type.startsWith('image/') ||
          /\.(png|jpe?g|gif|bmp|tiff?|webp)$/i.test(f.name);
        return { file: f, isImg, url: isImg ? URL.createObjectURL(f) : null };
      }),
    [value],
  );
  useEffect(
    () => () => {
      previews.forEach((p) => p.url && URL.revokeObjectURL(p.url));
    },
    [previews],
  );

  const addFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const merged = [...value];
    const bad: string[] = [];
    Array.from(list).forEach((f) => {
      const ok = ALLOWED.includes(extOf(f.name)) || f.type.startsWith('image/');
      if (!ok) {
        bad.push(f.name);
        return;
      }
      if (f.size === 0) return;
      const dup = merged.some(
        (x) => x.name === f.name && x.size === f.size && x.lastModified === f.lastModified,
      );
      if (!dup) merged.push(f);
    });
    setErr(bad.length ? `지원하지 않는 형식이에요: ${bad.join(', ')}` : null);
    onChange(merged);
    setCurrent(Math.max(0, merged.length - 1)); // 방금 추가한 장을 크게
    // 스캔 애니메이션 (감속 환경에선 즉시 done)
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (scanTimer.current) clearTimeout(scanTimer.current);
    setPhase('scanning');
    scanTimer.current = setTimeout(() => setPhase('done'), reduce ? 0 : 1800);
  };

  const openCam = () => camRef.current?.click();
  const openFile = () => fileRef.current?.click();
  const openPrimary = () => (conf.primary === 'cam' ? openCam() : openFile());

  const removeAt = (i: number) => {
    const next = value.filter((_, idx) => idx !== i);
    onChange(next);
    if (next.length === 0) setPhase('idle');
  };

  const resetInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(e.target.files);
    e.target.value = '';
  };

  const camBtnCls = conf.primary === 'cam' ? styles.btnPrimary : styles.btnSecondary;
  const fileBtnCls = conf.primary === 'file' ? styles.btnPrimary : styles.btnSecondary;
  const camBtn = (
    <button type="button" className={camBtnCls} onClick={openCam}>
      <CamIcon />
      {conf.camLabel}
    </button>
  );
  const fileBtn = (
    <button type="button" className={fileBtnCls} onClick={openFile}>
      <FileIcon />
      {conf.fileLabel}
    </button>
  );

  return (
    <div className={styles.wrap}>
      {err && <div className={styles.err}>{err}</div>}

      <input
        ref={camRef}
        type="file"
        accept={ACCEPT_IMAGE}
        capture="environment"
        multiple
        className={styles.hidden}
        onChange={resetInput}
      />
      <input
        ref={fileRef}
        type="file"
        multiple
        className={styles.hidden}
        onChange={resetInput}
      />

      {phase === 'done' ? (
        (() => {
          const cur = previews[Math.min(current, previews.length - 1)];
          return (
            <>
              <div className={styles.doneHead}>올린 문서 {value.length}장</div>
              <p className={styles.doneSub}>
                크게 보고 글자가 잘 보이는지 확인하세요.
              </p>

              {/* 큰 미리보기 — 현재 장 */}
              <div className={styles.bigPreview}>
                {cur?.isImg && cur.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={cur.url}
                    alt={`${current + 1}쪽 미리보기`}
                    className={styles.bigImg}
                  />
                ) : (
                  <div className={styles.bigDoc}>
                    <FileIcon />
                    <span className={styles.bigDocName}>{cur?.file.name}</span>
                  </div>
                )}
                <span className={styles.bigNo}>{current + 1}</span>
                <button
                  type="button"
                  className={styles.bigDel}
                  onClick={() => removeAt(current)}
                  aria-label={`${current + 1}장 삭제`}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" aria-hidden>
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>

              {/* 썸네일 줄 — 현재 장 링 + 끝에 + 추가 */}
              <div className={styles.thumbs}>
                {previews.map((p, i) => (
                  <button
                    type="button"
                    key={`${p.file.name}-${p.file.size}-${p.file.lastModified}-${i}`}
                    className={i === current ? styles.thumbOn : styles.thumb}
                    onClick={() => setCurrent(i)}
                    aria-label={`${i + 1}장 보기`}
                  >
                    {p.isImg && p.url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.url} alt="" className={styles.thumbImg} />
                    ) : (
                      <FileIcon />
                    )}
                    <span className={styles.thumbNo}>{i + 1}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className={styles.thumbAdd}
                  onClick={openPrimary}
                  aria-label="더 추가"
                >
                  +
                </button>
              </div>

              <div className={styles.tiny}>
                <ShieldIcon />
                검토 후 즉시 삭제
              </div>
            </>
          );
        })()
      ) : (
        <>
          <div className={styles.hero}>
            <div className={`${styles.pic} ${phase === 'scanning' ? styles.scanning : ''}`}>
              <div className={styles.paper}>
                <span className={`${styles.ln} ${styles.lnT}`} />
                <span className={`${styles.ln} ${styles.lnA}`} />
                <span className={`${styles.ln} ${styles.lnB}`} />
                <span className={`${styles.ln} ${styles.lnC}`} />
                <span className={`${styles.ln} ${styles.lnD}`} />
                <span className={`${styles.ln} ${styles.lnE}`} />
                <span className={styles.beam} />
              </div>
              <div className={styles.lens}>
                <CamIcon />
              </div>
            </div>
            <div className={styles.body}>
              <h2 className={styles.h}>
                {phase === 'scanning' ? '글자를 읽고 있어요…' : conf.h}
              </h2>
              <p className={styles.p}>
                {phase === 'scanning'
                  ? '문서가 또렷하면 더 정확해요. 잠시만요.'
                  : conf.p}
              </p>
              {conf.primary === 'cam' ? (
                <>
                  {camBtn}
                  {fileBtn}
                </>
              ) : (
                <>
                  {fileBtn}
                  {camBtn}
                </>
              )}
            </div>
          </div>
          <div className={styles.tiny}>
            <ShieldIcon />
            검토 후 즉시 삭제
          </div>
        </>
      )}
    </div>
  );
}
