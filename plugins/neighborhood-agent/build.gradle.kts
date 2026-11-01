plugins {
    java
}

group = "com.neighborhood"
version = "2.0.0"

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
    maven("https://maven.enginehub.org/repo/")
}

dependencies {
    compileOnly("io.papermc.paper:paper-api:1.21.4-R0.1-SNAPSHOT")
    compileOnly("com.google.code.gson:gson:2.11.0")
    compileOnly("com.fastasyncworldedit:FastAsyncWorldEdit-Core:2.15.3")
    compileOnly("com.fastasyncworldedit:FastAsyncWorldEdit-Bukkit:2.15.3") {
        isTransitive = false
    }
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("com.google.code.gson:gson:2.11.0")
}

tasks.test {
    useJUnitPlatform()
}

java {
    val target = JavaVersion.VERSION_21
    sourceCompatibility = target
    targetCompatibility = target
}

tasks.processResources {
    val props = mapOf("version" to version)
    inputs.properties(props)
    filesMatching("plugin.yml") {
        expand(props)
    }
}

tasks.jar {
    archiveFileName.set("NeighborhoodAgent.jar")
}
