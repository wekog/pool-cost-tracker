FROM node:20-alpine AS build

WORKDIR /app
COPY web/package.json /app/package.json
RUN npm install
COPY web /app
RUN npm run build

FROM nginx:alpine

COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8501
CMD ["nginx", "-g", "daemon off;"]
