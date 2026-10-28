{{- define "graphy.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "graphy.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "graphy.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "graphy.backendImage" -}}
{{ .Values.image.backend.repository }}:{{ .Values.image.backend.tag | default .Chart.AppVersion }}
{{- end -}}

{{- define "graphy.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}{{ include "graphy.fullname" . }}{{- else -}}default{{- end -}}
{{- end -}}

{{/* Shared pod settings for every backend container (api, migrations). */}}
{{- define "graphy.backendContainer" -}}
image: {{ include "graphy.backendImage" .root }}
imagePullPolicy: {{ .root.Values.image.pullPolicy }}
{{- /* Config is inlined rather than read from a ConfigMap so the pre-install migration
       hook, which runs before any chart resource exists, sees the same settings. */}}
env:
  {{- range $key, $value := .root.Values.config }}
  - name: GRAPHY_{{ $key }}
    value: {{ $value | quote }}
  {{- end }}
envFrom:
  - secretRef:
      name: {{ .root.Values.existingSecret }}
securityContext:
  {{- toYaml .root.Values.securityContext | nindent 2 }}
volumeMounts:
  - name: tmp
    mountPath: /tmp
{{- end -}}

{{- define "graphy.podSpec" -}}
{{- if not .hook }}
serviceAccountName: {{ include "graphy.serviceAccountName" .root }}
{{- end }}
securityContext:
  {{- toYaml .root.Values.podSecurityContext | nindent 2 }}
{{- with .root.Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
volumes:
  - name: tmp
    emptyDir: {}
{{- end -}}
