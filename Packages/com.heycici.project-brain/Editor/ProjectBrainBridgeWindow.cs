using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace HeyCici.ProjectBrain.Editor
{
	public sealed class ProjectBrainBridgeWindow : EditorWindow
	{
		private const string PackageVersion = "0.2.0";
		private const string DocumentationUrl =
			"https://github.com/orange91pku/" +
			"unity-ai-project-brain/blob/main/docs/UPM_INSTALL.md";

		private Vector2 _scrollPosition;

		[MenuItem("Tools/HeyCici/Project Brain")]
		public static void Open()
		{
			ProjectBrainBridgeWindow window =
				GetWindow<ProjectBrainBridgeWindow>();
			window.titleContent = new GUIContent("Project Brain");
			window.minSize = new Vector2(520f, 430f);
			window.Show();
		}

		[MenuItem("Tools/HeyCici/Project Brain/Copy Project Context JSON")]
		public static void CopyProjectContextFromMenu()
		{
			EditorGUIUtility.systemCopyBuffer = BuildContextJson();
			Debug.Log(
				"[Project Brain] Copied read-only Unity project context JSON.");
		}

		private void OnGUI()
		{
			_scrollPosition = EditorGUILayout.BeginScrollView(_scrollPosition);

			EditorGUILayout.LabelField(
				"Unity AI Project Brain",
				EditorStyles.boldLabel);
			EditorGUILayout.LabelField(
				"Read-only Unity identity bridge",
				EditorStyles.miniLabel);
			EditorGUILayout.Space();

			string unityProjectRoot = GetUnityProjectRoot();
			string repositoryRoot = FindRepositoryRoot(unityProjectRoot);

			EditorGUILayout.LabelField("Package", PackageVersion);
			EditorGUILayout.LabelField("Unity", Application.unityVersion);
			EditorGUILayout.LabelField("Project", unityProjectRoot);
			EditorGUILayout.LabelField("Repository", repositoryRoot);

			bool forceText =
				EditorSettings.serializationMode == SerializationMode.ForceText;
			EditorGUILayout.Space();
			EditorGUILayout.HelpBox(
				forceText
					? "Asset Serialization is Force Text. Scene, prefab and " +
						"asset relationships are visible to Project Brain."
					: "Set Project Settings > Editor > Asset Serialization " +
						"Mode to Force Text for complete Unity graph evidence.",
				forceText ? MessageType.Info : MessageType.Warning);

			EditorGUILayout.Space();
			EditorGUILayout.LabelField("Bootstrap", EditorStyles.boldLabel);
			if (GUILayout.Button("Copy Project Context JSON"))
			{
				CopyToClipboard(
					BuildContextJson(),
					"Project context JSON copied.");
			}
			if (GUILayout.Button("Copy Backend Install Command"))
			{
				CopyToClipboard(
					BuildBackendInstallCommand(),
					"Backend install command copied.");
			}
			if (GUILayout.Button("Copy Context API Command"))
			{
				CopyToClipboard(
					BuildContextApiCommand(repositoryRoot, unityProjectRoot),
					"Context API command copied.");
			}
			if (GUILayout.Button("Open Installation Guide"))
			{
				Application.OpenURL(DocumentationUrl);
			}

			EditorGUILayout.Space();
			EditorGUILayout.HelpBox(
				"The package never edits Unity assets or starts external " +
				"processes automatically. Backend installation, indexing and " +
				"server startup remain explicit operator actions.",
				MessageType.None);

			EditorGUILayout.EndScrollView();
		}

		private void CopyToClipboard(string value, string notification)
		{
			EditorGUIUtility.systemCopyBuffer = value;
			ShowNotification(new GUIContent(notification));
		}

		private static string BuildContextJson()
		{
			string unityProjectRoot = GetUnityProjectRoot();
			ProjectContextDescriptor descriptor =
				new ProjectContextDescriptor
				{
					schema =
						"com.heycici.project-brain/unity-project-context/v1",
					packageVersion = PackageVersion,
					generatedUtc = DateTime.UtcNow.ToString("O"),
					unityVersion = Application.unityVersion,
					repositoryRoot = FindRepositoryRoot(unityProjectRoot),
					unityProjectRoot = unityProjectRoot,
					assetsRoot = Path.Combine(unityProjectRoot, "Assets"),
					serializationMode =
						EditorSettings.serializationMode.ToString(),
					activeBuildTarget =
						EditorUserBuildSettings.activeBuildTarget.ToString()
				};
			return JsonUtility.ToJson(descriptor, true);
		}

		private static string BuildBackendInstallCommand()
		{
			return "python -m pip install " +
				"\"unity-ai-project-brain @ git+" +
				"https://github.com/orange91pku/" +
				"unity-ai-project-brain.git@v0.2.0\"";
		}

		private static string BuildContextApiCommand(
			string repositoryRoot,
			string unityProjectRoot)
		{
			string graphPath = Path.Combine(
				repositoryRoot,
				".project-brain",
				"unity-graph.sqlite");
			return "python -m project_brain.context_api serve" +
				" --graph " + Quote(graphPath) +
				" --repository " + Quote(repositoryRoot) +
				" --unity-project " + Quote(unityProjectRoot) +
				" --host 127.0.0.1 --port 8765";
		}

		private static string GetUnityProjectRoot()
		{
			return Path.GetFullPath(
				Path.Combine(Application.dataPath, ".."));
		}

		private static string FindRepositoryRoot(string unityProjectRoot)
		{
			DirectoryInfo current = new DirectoryInfo(unityProjectRoot);
			while (current != null)
			{
				string marker = Path.Combine(current.FullName, ".git");
				if (Directory.Exists(marker) || File.Exists(marker))
				{
					return current.FullName;
				}
				current = current.Parent;
			}
			return unityProjectRoot;
		}

		private static string Quote(string value)
		{
			return "\"" + value.Replace("\"", "\\\"") + "\"";
		}

		[Serializable]
		private sealed class ProjectContextDescriptor
		{
			public string schema;
			public string packageVersion;
			public string generatedUtc;
			public string unityVersion;
			public string repositoryRoot;
			public string unityProjectRoot;
			public string assetsRoot;
			public string serializationMode;
			public string activeBuildTarget;
		}
	}
}
