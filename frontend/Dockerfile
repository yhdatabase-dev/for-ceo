# 프론트엔드(Next.js 14) 프로덕션 이미지 — build 후 `next start`.
# BFF·관리자 로그인이 서버사이드라 정적 export 가 아니라 Node 런타임으로 띄운다.
FROM node:24.21.0-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* 는 빌드 시점에 인라인됨 → 백엔드 내부 주소를 빌드 ARG 로 주입
# (compose 네트워크에서 backend 서비스명:포트). 서버사이드 BFF 만 사용.
ARG NEXT_PUBLIC_API_BASE=http://backend:8080
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
# 하위경로 배포(moellab.info/for-ceo)면 --build-arg NEXT_PUBLIC_BASE_PATH=/for-ceo.
# 루트 배포면 빈 값(기본) → basePath 없음. NEXT_PUBLIC_* 라 빌드 시 인라인.
ARG NEXT_PUBLIC_BASE_PATH=
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH
RUN npm run build

FROM node:24.21.0-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# 비-root 실행(OWASP A05 보안설정오류/컨테이너 하드닝) — node:alpine 내장 'node'(uid 1000) 사용.
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/next.config.mjs ./next.config.mjs
USER node
EXPOSE 3000
# package.json: "start": "next start -p 3000"
CMD ["npm", "run", "start"]
