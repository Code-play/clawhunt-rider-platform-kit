# 前端静态站点镜像：构建 h5 与 admin 两个 Vite 应用，交给 nginx 托管
# 用途：给 `docker compose up` 提供 http://127.0.0.1:8080/h5/ 与 /admin/ 的可点通入口
# 说明：默认把前端指向同源 /proxy（nginx 反代到 api:8000），避免跨域；后端不可用时前端自动回落 mock。

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
COPY h5/package.json ./h5/package.json
COPY admin/package.json ./admin/package.json
RUN npm install --no-audit --no-fund
COPY . .
# 同源代理前缀：浏览器请求 /proxy/api/v1/... → nginx → api:8000/api/v1/...
ARG VITE_API_BASE=/proxy
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/h5/dist /usr/share/nginx/html/h5
COPY --from=build /app/admin/dist /usr/share/nginx/html/admin
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
