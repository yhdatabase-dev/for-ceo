/**
 * BFF — 클라이언트 `/api/cgr/*` → 백엔드 FastAPI `{API_BASE}/api/cgr/*` 프록시.
 *
 * 서버측에서만 `CGR_API_KEY` 환경변수 사용 → 클라이언트에 키 노출 없음.
 * GET / POST 모두 처리 (파일 업로드 multipart 포함).
 */
import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8503';
const API_PREFIX = '/api/cgr';
const API_KEY = process.env.CGR_API_KEY ?? '';

/**
 * Next.js → 백엔드 헤더 빌더.
 *
 * - multipart: Content-Type 자체를 제외 (fetch 가 새 boundary 로 자동 설정해야 함)
 * - json / 기타: 원본 Content-Type 그대로 forward
 */
function buildHeaders(req: NextRequest, isMultipart: boolean): HeadersInit {
  const h: Record<string, string> = {};
  const ct = req.headers.get('content-type');
  if (ct && !isMultipart) {
    h['Content-Type'] = ct;
  }
  // 인증 키 — 관리자 기능 제외로 관리자 키 주입 경로는 두지 않는다.
  if (API_KEY) {
    h['X-API-Key'] = API_KEY;
  }
  return h;
}

/** 통합 핸들러 — GET/POST/PUT/DELETE 모두 동일 로직. */
async function handler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const parts = (await params).path ?? [];

  const url = `${API_BASE}${API_PREFIX}/${parts.join('/')}${req.nextUrl.search}`;

  const ct = req.headers.get('content-type') ?? '';
  const isMultipart = ct.startsWith('multipart/');

  const init: RequestInit = {
    method: req.method,
    headers: buildHeaders(req, isMultipart),
    // 백엔드가 302 redirect 를 반환하는 경우 (예: 외부 사이트로 redirect)
    // — Next.js 의 fetch 가 자동
    // follow 하면 외부 사이트로 직접 호출 가다 실패한다. 'manual' 로 두면 302
    // 응답 자체를 클라이언트(브라우저) 로 그대로 forward 해서 브라우저가 따라간다.
    redirect: 'manual',
  };

  if (!['GET', 'HEAD'].includes(req.method)) {
    if (isMultipart) {
      // ReadableStream body 직접 forward 시 multipart boundary 가 깨지는 경우가 있어
      // FormData 로 재구성 후 보냄 — fetch 가 새 boundary 로 Content-Type 을 자동 설정.
      try {
        const form = await req.formData();
        const fresh = new FormData();
        for (const [k, v] of form.entries()) {
          fresh.append(k, v);
        }
        init.body = fresh;
      } catch (err) {
        return NextResponse.json(
          {
            detail: `multipart 파싱 실패: ${err instanceof Error ? err.message : String(err)}`,
          },
          { status: 400 },
        );
      }
    } else {
      // JSON 등 — 텍스트로 읽어서 그대로 forward
      const text = await req.text();
      init.body = text;
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (err) {
    return NextResponse.json(
      {
        detail: `백엔드 호출 실패: ${err instanceof Error ? err.message : String(err)}`,
        upstream: url,
      },
      { status: 502 },
    );
  }

  // 응답 body·헤더 forward
  // 주의: undici(Node fetch)는 gzip 응답을 arrayBuffer() 시 자동 압축해제한다.
  // 따라서 body 는 압축해제된 원본인데, 업스트림의 content-encoding(gzip)과
  // content-length(압축 크기)를 그대로 넘기면 브라우저가 압축 크기만큼만 읽고
  // 끊어버려 'Unterminated JSON' 이 난다. 두 헤더 모두 반드시 제거하고
  // NextResponse 가 실제 body 길이로 다시 계산하도록 둔다.
  const body = await upstream.arrayBuffer();
  const headers = new Headers();
  const STRIP = ['content-encoding', 'transfer-encoding', 'content-length'];
  upstream.headers.forEach((v, k) => {
    if (!STRIP.includes(k.toLowerCase())) {
      headers.set(k, v);
    }
  });

  return new NextResponse(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;

// Node.js 런타임 — multipart formData 지원 + 파일 업로드 가능
export const runtime = 'nodejs';
// 백엔드 검토가 60~90초 걸리므로 BFF 타임아웃 여유있게
export const maxDuration = 120;
