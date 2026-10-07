/**
 * 업로드 전처리 — 이미지 압축 + 다중 파일 텍스트 추출.
 *
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.06.18      kimzion77   최초 생성
 * 2026.10.01      이시영      임금명세서·노무제공자 계약서·관리자 기능 삭제
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.06.18
 */
/**
 * 업로드 전처리 — 이미지 압축 + 다중 파일 텍스트 추출.
 *
 * 왜 압축이 필요한가:
 *   휴대폰 카메라 사진은 보통 3~12MB 인데, Vercel 서버리스 함수(BFF)의 요청
 *   본문 한도가 약 4.5MB 라 그대로 올리면 413(entity too large)으로 분석이
 *   막힌다. 그래서 이미지면 업로드 직전 canvas 로 리사이즈·JPEG 재인코딩해
 *   목표 크기 이하로 줄인다. 문서(docx/hwp/pdf/txt)는 손대지 않는다.
 *
 * 다중 파일(여러 장 촬영·여러 페이지):
 *   각 파일을 추출 엔드포인트에 순서대로 태우고, 추출 텍스트를 페이지 구분자와
 *   함께 이어 붙여 하나의 문서 텍스트로 만든다 (백엔드 변경 없이 다중 페이지 지원).
 */

/** Vercel 본문 한도(~4.5MB) 안쪽으로 — 멀티파트 오버헤드 여유 두고 목표치. */
const TARGET_BYTES = 3.4 * 1024 * 1024;
/** 첫 시도 최대 변(긴 쪽) 픽셀. 너무 크면 OCR 도 느리고 용량도 커진다. */
const MAX_DIM = 2400;
/** 더 줄여야 할 때 단계적으로 낮출 최소 변. */
const MIN_DIM = 1400;

function isImageFile(file: File): boolean {
  return (
    file.type.startsWith('image/') ||
    /\.(png|jpe?g|gif|bmp|tiff?|webp|heic|heif)$/i.test(file.name)
  );
}

function baseName(name: string): string {
  const i = name.lastIndexOf('.');
  return (i < 0 ? name : name.slice(0, i)) || 'image';
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('이미지를 불러오지 못했어요.'));
    };
    img.src = url;
  });
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob((b) => resolve(b), 'image/jpeg', quality);
  });
}

/**
 * 이미지 파일 1장을 목표 크기 이하의 JPEG 으로 압축.
 *
 * 이미 작은(≤TARGET) 이미지나 압축이 불가능한 환경(canvas 미지원)에서는
 * 원본을 그대로 반환한다 — 안전 폴백.
 */
export async function compressImageFile(file: File): Promise<File> {
  if (!isImageFile(file)) return file;
  // 이미 충분히 작으면 그대로 (단, HEIC 등은 canvas 변환이 필요할 수 있어 통과시켜 시도)
  if (file.size <= TARGET_BYTES && /image\/(jpe?g|png|webp)/i.test(file.type)) {
    return file;
  }

  let img: HTMLImageElement;
  try {
    img = await loadImage(file);
  } catch {
    return file; // 디코딩 실패 — 원본 그대로 (백엔드 OCR 에 맡김)
  }

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return file;

  // 단계적 시도: (변 크기, 품질) 조합을 점점 낮춰 목표 이하로.
  const dims = [MAX_DIM, 2000, 1700, MIN_DIM];
  const qualities = [0.85, 0.75, 0.65, 0.55];

  let best: Blob | null = null;
  for (const dim of dims) {
    const scale = Math.min(1, dim / Math.max(img.width, img.height));
    canvas.width = Math.max(1, Math.round(img.width * scale));
    canvas.height = Math.max(1, Math.round(img.height * scale));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    for (const q of qualities) {
      const blob = await canvasToBlob(canvas, q);
      if (!blob) continue;
      best = blob; // 마지막(가장 작은) 결과를 폴백으로 유지
      if (blob.size <= TARGET_BYTES) {
        return new File([blob], `${baseName(file.name)}.jpg`, {
          type: 'image/jpeg',
          lastModified: file.lastModified,
        });
      }
    }
  }

  // 목표를 못 맞췄어도 가장 작은 결과가 원본보다 작으면 그걸 쓴다.
  if (best && best.size < file.size) {
    return new File([best], `${baseName(file.name)}.jpg`, {
      type: 'image/jpeg',
      lastModified: file.lastModified,
    });
  }
  return file;
}

/** 결과 화면 좌측 미리보기용 최대 변(긴 쪽) — 표시용이라 작게. */
const PREVIEW_MAX_DIM = 1400;

/**
 * 업로드 이미지를 **결과 화면 미리보기용 data: URL** 로 변환.
 *
 * 왜: 업로드 시 만든 blob URL 은 새로고침·검토 이력 복원 시 무효화돼 좌측 원본
 * 사진이 사라진다(저장소에 직렬화 불가). data: URL 은 저장소에 그대로 남길 수
 * 있어, 새로고침/이력에서도 사진을 다시 볼 수 있다. 표시 전용이라 1400px·JPEG
 * 0.72 로 다운스케일해 용량을 줄인다(localStorage 용량 보호).
 *
 * 이미지가 아니거나 변환 실패 시 null → 호출부에서 blob URL 로 폴백.
 */
export async function fileToDisplayDataUrl(file: File): Promise<string | null> {
  if (!isImageFile(file)) return null;
  let img: HTMLImageElement;
  try {
    img = await loadImage(file);
  } catch {
    return null;
  }
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const scale = Math.min(1, PREVIEW_MAX_DIM / Math.max(img.width, img.height));
  canvas.width = Math.max(1, Math.round(img.width * scale));
  canvas.height = Math.max(1, Math.round(img.height * scale));
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  try {
    return canvas.toDataURL('image/jpeg', 0.72);
  } catch {
    return null; // tainted canvas 등 — 폴백
  }
}

/** 페이지 구분자 — 다중 파일의 추출 텍스트를 이어붙일 때. */
function pageSeparator(idx: number, total: number): string {
  return total > 1 ? `\n\n──────── (${idx + 1}/${total} 페이지) ────────\n\n` : '';
}

type ExtractFn = (
  file: File,
  opts?: { signal?: AbortSignal; caseId?: string; service?: string },
) => Promise<{ extracted_text: string }>;

/**
 * 여러 파일을 추출 엔드포인트에 순서대로 태워 텍스트를 이어붙인다.
 *
 * - 이미지는 추출 전 자동 압축 (413 방지)
 * - 단일 파일이면 구분자 없이 그 텍스트만
 * - onProgress(현재, 전체) 로 진행 표시 가능
 */
export async function extractAllText(
  files: File[],
  extractFn: ExtractFn,
  opts: {
    signal?: AbortSignal;
    onProgress?: (done: number, total: number) => void;
    /** 검토 건 번호 — 업로드 기록을 검토 건과 연결(여러 장이면 모두 같은 번호). */
    caseId?: string;
    /** 보관 서비스 라벨 — 근로계약서 / 취업규칙. */
    service?: string;
    /**
     * 첫 장 추출 결과 — 첫 장은 검토 건 번호(case_id)를 서버에서 받으려고 미리 접수하므로
     * 여기서는 그 결과만 기다린다.
     * 프로그램명세서 AI-P02-001: case_id 는 서버 발급, 첫 장 응답의 번호를 이후 장에 싣는다.
     * (기존: 모든 장을 이 함수에서 접수)
     */
    firstResult?: Promise<{ extracted_text: string }>;
  } = {},
): Promise<string> {
  const list = files.length > 0 ? files : [];
  const parts: string[] = [];
  for (let i = 0; i < list.length; i += 1) {
    const { extracted_text } =
      i === 0 && opts.firstResult
        ? await opts.firstResult
        : await extractFn(await compressImageFile(list[i]), {
            signal: opts.signal,
            caseId: opts.caseId,
            service: opts.service,
          });
    parts.push(pageSeparator(i, list.length) + (extracted_text ?? ''));
    opts.onProgress?.(i + 1, list.length);
  }
  return parts.join('').trim();
}
